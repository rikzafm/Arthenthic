"""
Similarity scoring engine.
Combines photo texture cosine similarity and depth relief roughness into a total score in basis points (0..10000).
Checks flat-print pass/fail gate.
Supports single-point and guided multi-point (8-point spatial grid) matching with tolerance gating.
"""

import numpy as np
from typing import Dict, Any, List, Optional

DEFAULT_MIN_SIMILARITY_BPS = 8800  # 88.0%

POINT_SPATIAL_NAMES = {
    1: "Top-Left Corner",
    2: "Top-Center",
    3: "Top-Right Corner",
    4: "Center-Left",
    5: "Center-Right",
    6: "Bottom-Left Corner",
    7: "Bottom-Center",
    8: "Bottom-Right Corner"
}

class SimilarityEngine:
    def __init__(self, min_similarity_bps: int = DEFAULT_MIN_SIMILARITY_BPS):
        self.min_similarity_bps = min_similarity_bps

    def compare(
        self,
        genesis_vector: np.ndarray,
        verify_vector: np.ndarray,
        genesis_depth: Dict[str, Any],
        verify_depth: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare new capture features against genesis baseline.
        """
        # 1. Photo cosine similarity
        norm_g = np.linalg.norm(genesis_vector)
        norm_v = np.linalg.norm(verify_vector)
        if norm_g > 1e-6 and norm_v > 1e-6:
            photo_cos = float(np.dot(genesis_vector, verify_vector) / (norm_g * norm_v))
        else:
            photo_cos = 0.0
        # Clip to [0, 1]
        photo_score = max(0.0, min(1.0, photo_cos))

        # 2. Depth relief similarity
        g_rough = genesis_depth.get("relief_roughness", 0.45)
        v_rough = verify_depth.get("relief_roughness", 0.45)
        diff = abs(g_rough - v_rough)
        depth_score = max(0.0, 1.0 - (diff / max(g_rough, 0.1)))

        # 3. Flat print check
        flat_print_passed = bool(verify_depth.get("flat_print_passed", True))

        # 4. Weighted combination: 70% photo texture, 30% LiDAR relief
        combined = (photo_score * 0.70) + (depth_score * 0.30)
        if not flat_print_passed:
            combined *= 0.5  # Heavy penalty if detected as flat print

        similarity_bps = int(round(combined * 10000))
        is_authentic = similarity_bps >= self.min_similarity_bps and flat_print_passed

        return {
            "similarityBps": similarity_bps,
            "isAuthentic": is_authentic,
            "thresholdBps": self.min_similarity_bps,
            "branches": {
                "photoTexturePct": int(round(photo_score * 100)),
                "lidarReliefPct": int(round(depth_score * 100)),
                "flatPrintPassed": flat_print_passed
            }
        }

    def compare_multipoint(
        self,
        genesis_points: List[Dict[str, Any]],
        verify_points: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Multi-point spatial comparison (e.g. 8 points across canvas).
        Requires >= 7 of 8 points (or >= total - 1) to pass individual threshold
        AND presentation attack check (flat-print) to pass.
        """
        total_points = len(verify_points)
        if total_points == 0:
            return {
                "similarityBps": 0,
                "isAuthentic": False,
                "thresholdBps": self.min_similarity_bps,
                "pointsPassed": 0,
                "totalPoints": 0,
                "pointBreakdown": [],
                "branches": {
                    "photoTexturePct": 0,
                    "lidarReliefPct": 0,
                    "flatPrintPassed": False
                }
            }

        # If genesis has only 1 pooled baseline point, compare all verify points against it
        has_matched_genesis = len(genesis_points) == total_points

        point_results = []
        points_passed = 0
        total_photo_score = 0.0
        total_depth_score = 0.0
        all_flat_prints_passed = True

        for idx, v_item in enumerate(verify_points):
            pt_idx = v_item.get("pointIndex", idx + 1)
            g_item = genesis_points[idx] if has_matched_genesis else genesis_points[0]

            g_vec = g_item["vector"]
            v_vec = v_item["vector"]
            g_depth = g_item.get("depth_stats", {"relief_roughness": 0.45, "flat_print_passed": True})
            v_depth = v_item.get("depth_stats", {"relief_roughness": 0.45, "flat_print_passed": True})

            res = self.compare(g_vec, v_vec, g_depth, v_depth)
            pt_passed = res["isAuthentic"]
            if pt_passed:
                points_passed += 1

            total_photo_score += res["branches"]["photoTexturePct"]
            total_depth_score += res["branches"]["lidarReliefPct"]
            if not res["branches"]["flatPrintPassed"]:
                all_flat_prints_passed = False

            point_results.append({
                "pointIndex": pt_idx,
                "name": POINT_SPATIAL_NAMES.get(pt_idx, f"Point {pt_idx}"),
                "similarityBps": res["similarityBps"],
                "similarityPct": res["similarityBps"] / 100.0,
                "passed": pt_passed,
                "flatPrintPassed": res["branches"]["flatPrintPassed"],
                "reliefRoughnessMm": v_depth.get("relief_roughness", 0.0)
            })

        avg_similarity_bps = int(round(np.mean([p["similarityBps"] for p in point_results])))
        avg_photo_pct = int(round(total_photo_score / total_points))
        avg_depth_pct = int(round(total_depth_score / total_points))

        # Tolerance rule: >= 7 of 8 points (or >= total - 1 for general N)
        required_pass_count = max(1, total_points - 1) if total_points >= 4 else total_points
        is_authentic = (
            points_passed >= required_pass_count and
            avg_similarity_bps >= self.min_similarity_bps and
            all_flat_prints_passed
        )

        return {
            "similarityBps": avg_similarity_bps,
            "isAuthentic": is_authentic,
            "thresholdBps": self.min_similarity_bps,
            "pointsPassed": points_passed,
            "totalPoints": total_points,
            "requiredPoints": required_pass_count,
            "pointBreakdown": point_results,
            "branches": {
                "photoTexturePct": avg_photo_pct,
                "lidarReliefPct": avg_depth_pct,
                "flatPrintPassed": all_flat_prints_passed
            }
        }

similarity_engine = SimilarityEngine()
