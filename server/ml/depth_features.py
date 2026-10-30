"""
Depth feature extractor & plane fitting.
Uses camera intrinsics and depth map to backproject 3D points,
fits a planar model to find the canvas substrate,
and computes relief micro-variance and a flatness score (flat print detection).
"""

import numpy as np
from typing import Dict, Any, Tuple

class DepthFeatureExtractor:
    def __init__(self):
        pass

    def backproject(self, depth_map: np.ndarray, intrinsics: Dict[str, float]) -> np.ndarray:
        """
        Backproject 2D depth map (H, W) into 3D camera coordinates (N, 3).
        intrinsics contains fx, fy, cx, cy.
        """
        H, W = depth_map.shape
        fx = intrinsics.get("fx", 1400.0)
        fy = intrinsics.get("fy", 1400.0)
        cx = intrinsics.get("cx", W / 2.0)
        cy = intrinsics.get("cy", H / 2.0)

        u = np.arange(W)
        v = np.arange(H)
        uu, vv = np.meshgrid(u, v)

        z = depth_map.astype(np.float32)
        valid_mask = (z > 0.05) & (z < 1.0) & np.isfinite(z)

        x = (uu[valid_mask] - cx) * z[valid_mask] / fx
        y = (vv[valid_mask] - cy) * z[valid_mask] / fy
        z_valid = z[valid_mask]

        points = np.stack([x, y, z_valid], axis=-1)
        return points

    def fit_plane_and_residuals(self, points: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """
        Fit plane Ax + By + Cz + D = 0 using SVD on points.
        Returns:
            plane_normal: (3,)
            residual_variance: variance of perpendicular distances (relief roughness)
            flatness_score: 1.0 = mathematically flat, 0.0 = high texture/roughness
        """
        if len(points) < 50:
            return np.array([0, 0, 1]), 0.0, 1.0

        centroid = np.mean(points, axis=0)
        centered = points - centroid

        # Fast 3x3 covariance matrix eigendecomposition
        cov = np.dot(centered.T, centered)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        normal = eigenvectors[:, 0] # eigenvector corresponding to smallest eigenvalue

        # Distance from each point to the fitted plane
        distances = np.abs(np.dot(centered, normal))
        residual_variance = float(np.var(distances))
        residual_std_mm = float(np.std(distances) * 1000.0) # in millimeters

        return normal, residual_variance, residual_std_mm

    def extract_features(self, depth_bytes: bytes, intrinsics: Dict[str, float]) -> Dict[str, Any]:
        """
        Parse raw float16/float32 depth bytes and extract depth relief statistics.
        """
        # Expect 192x256 or 256x192 depth buffer or 128x128
        try:
            depth_arr = np.frombuffer(depth_bytes, dtype=np.float32)
            # Find approximate square or 4:3 dimension
            n = len(depth_arr)
            side = int(np.sqrt(n))
            if side * side == n:
                depth_map = depth_arr.reshape((side, side))
            elif n == 256 * 192:
                depth_map = depth_arr.reshape((256, 192))
            elif n == 192 * 256:
                depth_map = depth_arr.reshape((192, 256))
            else:
                depth_map = np.full((128, 128), 0.15, dtype=np.float32)
        except Exception:
            depth_map = np.full((128, 128), 0.15, dtype=np.float32)

        points = self.backproject(depth_map, intrinsics)
        normal, variance, std_mm = self.fit_plane_and_residuals(points)

        # Flat-print test: if depth variance is below the physical weave threshold, fail
        flat_print_passed = std_mm >= 0.20

        return {
            "plane_normal": normal.tolist(),
            "relief_roughness": std_mm,
            "variance": variance,
            "flat_print_passed": flat_print_passed
        }

depth_extractor = DepthFeatureExtractor()
