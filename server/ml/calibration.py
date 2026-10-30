"""
server/ml/calibration.py
Substrate Field Calibration & Adaptive Multi-Point Optical Engine (Phase Field-QA / Wave 3 Milestone 5).
Calibrates 8-point 256x192 LiDAR sceneDepth + Macro RGB thresholds across physical substrates:
- Linen Canvas (standard weave texture, 8800 bps baseline)
- Wood Panel (tight grain, 9000 bps baseline)
- Impasto Oil (heavy 3D knife relief, 8500 bps baseline, 40% depth weighting)
- Watercolor Cotton (fine tooth matte, 8900 bps baseline)
Includes LiDAR SNR computation, ambient lighting normalization, and adaptive tolerance bands.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Union
import numpy as np


class SubstrateType(str, Enum):
    LINEN_CANVAS = "LINEN_CANVAS"
    WOOD_PANEL = "WOOD_PANEL"
    IMPASTO_OIL = "IMPASTO_OIL"
    WATERCOLOR_COTTON = "WATERCOLOR_COTTON"


@dataclass(frozen=True)
class SubstrateProfile:
    substrate: SubstrateType
    display_name: str
    baseline_roughness_mm: float
    min_similarity_bps: int
    depth_weight: float
    roughness_tolerance_mm: float
    flat_print_min_roughness_mm: float


SUBSTRATE_PROFILES: Dict[SubstrateType, SubstrateProfile] = {
    SubstrateType.LINEN_CANVAS: SubstrateProfile(
        substrate=SubstrateType.LINEN_CANVAS,
        display_name="Linen Canvas",
        baseline_roughness_mm=0.45,
        min_similarity_bps=8800,
        depth_weight=0.30,
        roughness_tolerance_mm=0.20,
        flat_print_min_roughness_mm=0.20,
    ),
    SubstrateType.WOOD_PANEL: SubstrateProfile(
        substrate=SubstrateType.WOOD_PANEL,
        display_name="Wood Panel",
        baseline_roughness_mm=0.28,
        min_similarity_bps=9000,
        depth_weight=0.25,
        roughness_tolerance_mm=0.15,
        flat_print_min_roughness_mm=0.15,
    ),
    SubstrateType.IMPASTO_OIL: SubstrateProfile(
        substrate=SubstrateType.IMPASTO_OIL,
        display_name="Impasto Oil",
        baseline_roughness_mm=1.20,
        min_similarity_bps=8500,
        depth_weight=0.40,
        roughness_tolerance_mm=0.50,
        flat_print_min_roughness_mm=0.35,
    ),
    SubstrateType.WATERCOLOR_COTTON: SubstrateProfile(
        substrate=SubstrateType.WATERCOLOR_COTTON,
        display_name="Watercolor Cotton",
        baseline_roughness_mm=0.22,
        min_similarity_bps=8900,
        depth_weight=0.20,
        roughness_tolerance_mm=0.12,
        flat_print_min_roughness_mm=0.12,
    ),
}


class SubstrateCalibrationEngine:
    """
    Field sensor calibration engine for iPhone 15/16 Pro LiDAR (256x192 sceneDepth)
    and high-resolution macro photography under varying gallery illumination.
    """

    def __init__(self):
        self._profiles = SUBSTRATE_PROFILES

    def get_profile(self, substrate: Union[SubstrateType, str]) -> SubstrateProfile:
        if isinstance(substrate, str):
            try:
                substrate = SubstrateType(substrate)
            except ValueError:
                substrate = SubstrateType.LINEN_CANVAS
        return self._profiles.get(substrate, self._profiles[SubstrateType.LINEN_CANVAS])

    def calculate_depth_snr(
        self, depth_map: np.ndarray, noise_sigma: float = 0.00005
    ) -> float:
        """
        Computes the Signal-to-Noise Ratio (SNR in dB) of the LiDAR depth map.
        Signal = variance of actual structural relief.
        Noise = sensor point-spread variance (sigma^2).
        """
        clean_depth = depth_map[np.isfinite(depth_map) & (depth_map > 0.05)]
        if len(clean_depth) < 50:
            return 0.0

        signal_var = float(np.var(clean_depth))
        noise_var = max(noise_sigma ** 2, 1e-12)

        ratio = max(signal_var / noise_var, 1.0)
        snr_db = 10.0 * np.log10(ratio)
        return float(round(snr_db, 2))

    def normalize_lighting(
        self, rgb_image: np.ndarray, target_lux: float = 500.0, measured_lux: float = 80.0
    ) -> np.ndarray:
        """
        Normalizes Macro RGB frame exposure against varying museum/gallery lighting conditions.
        Uses gamma-corrected luminance scaling.
        """
        if measured_lux <= 0:
            measured_lux = 80.0
        ratio = target_lux / max(measured_lux, 10.0)
        gain = np.clip(ratio ** 0.5, 0.5, 3.0)

        normalized = np.clip(rgb_image.astype(np.float32) * gain, 0, 255).astype(np.uint8)
        return normalized

    def evaluate_substrate_calibration(
        self,
        substrate: Union[SubstrateType, str],
        depth_roughness_mm: float,
        photo_texture_pct: float,
        ambient_lux: float = 500.0,
    ) -> Dict[str, Any]:
        """
        Evaluates physical authenticity match against calibrated substrate baseline.
        Returns adapted score, gate checks, and substrate recommendations.
        """
        profile = self.get_profile(substrate)

        # 1. Flat print presentation attack gate
        flat_print_passed = depth_roughness_mm >= profile.flat_print_min_roughness_mm

        # 2. Depth relief similarity score
        diff = abs(depth_roughness_mm - profile.baseline_roughness_mm)
        tolerance = profile.roughness_tolerance_mm
        depth_score = max(0.0, 1.0 - (diff / max(tolerance * 2.0, 0.1)))

        # 3. Photo texture score (0..1)
        photo_score = max(0.0, min(1.0, photo_texture_pct / 100.0))

        # 4. Substrate-weighted combination
        depth_weight = profile.depth_weight
        photo_weight = 1.0 - depth_weight

        combined = (photo_score * photo_weight) + (depth_score * depth_weight)
        if not flat_print_passed:
            combined *= 0.5

        similarity_bps = int(round(combined * 10000))
        is_authentic = similarity_bps >= profile.min_similarity_bps and flat_print_passed

        return {
            "substrate": profile.substrate.value,
            "display_name": profile.display_name,
            "similarityBps": similarity_bps,
            "thresholdBps": profile.min_similarity_bps,
            "isAuthentic": is_authentic,
            "flatPrintPassed": flat_print_passed,
            "baselineRoughnessMm": profile.baseline_roughness_mm,
            "measuredRoughnessMm": depth_roughness_mm,
            "depthScorePct": int(round(depth_score * 100)),
            "photoScorePct": int(round(photo_score * 100)),
            "ambientLux": ambient_lux,
        }


substrate_engine = SubstrateCalibrationEngine()

