"""
Calibration evaluation script (Milestone 4).
Runs pairwise comparisons across:
- Same surface repeats (Genuine)
- Different surface scans (Impostor)
- Flat paper print attacks (Presentation attack)
Outputs metrics table, FAR, FRR, and threshold analysis.
"""

import os
import json
import sys
import numpy as np
from server.ml.embedder import embedder
from server.ml.depth_features import depth_extractor
from server.ml.similarity import similarity_engine

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))

def run_calibration(exit_on_completion: bool = True) -> bool:
    with open(os.path.join(FIXTURES_DIR, "intrinsics.json")) as f:
        intrinsics = json.load(f)

    # 1. Load genesis sample
    with open(os.path.join(FIXTURES_DIR, "canvas_sample_1.jpg"), "rb") as f:
        genesis_photo = f.read()
    with open(os.path.join(FIXTURES_DIR, "depth_sample_1.bin"), "rb") as f:
        genesis_depth_bytes = f.read()

    g_vec = embedder.extract_from_bytes(genesis_photo)
    g_depth = depth_extractor.extract_features(genesis_depth_bytes, intrinsics)

    # 2. Test genuine samples (samples 2..5)
    genuine_results = []
    genuine_scores = []
    for i in range(2, 6):
        with open(os.path.join(FIXTURES_DIR, f"canvas_sample_{i}.jpg"), "rb") as f:
            photo = f.read()
        with open(os.path.join(FIXTURES_DIR, f"depth_sample_{i}.bin"), "rb") as f:
            depth_bytes = f.read()

        vec = embedder.extract_from_bytes(photo)
        depth = depth_extractor.extract_features(depth_bytes, intrinsics)
        res = similarity_engine.compare(g_vec, vec, g_depth, depth)
        genuine_results.append((res, depth))
        genuine_scores.append(res["similarityBps"])

    # 3. Test impostor samples (different surfaces)
    impostor_results = []
    impostor_scores = []
    for i in range(1, 4):
        with open(os.path.join(FIXTURES_DIR, f"different_surface_{i}.jpg"), "rb") as f:
            photo = f.read()
        with open(os.path.join(FIXTURES_DIR, f"different_depth_{i}.bin"), "rb") as f:
            depth_bytes = f.read()

        vec = embedder.extract_from_bytes(photo)
        depth = depth_extractor.extract_features(depth_bytes, intrinsics)
        res = similarity_engine.compare(g_vec, vec, g_depth, depth)
        impostor_results.append((res, depth))
        impostor_scores.append(res["similarityBps"])

    # 4. Test flat-print attacks
    flat_results = []
    flat_scores = []
    for i in range(1, 3):
        with open(os.path.join(FIXTURES_DIR, f"flat_print_{i}.jpg"), "rb") as f:
            photo = f.read()
        with open(os.path.join(FIXTURES_DIR, f"flat_print_depth_{i}.bin"), "rb") as f:
            depth_bytes = f.read()

        vec = embedder.extract_from_bytes(photo)
        depth = depth_extractor.extract_features(depth_bytes, intrinsics)
        res = similarity_engine.compare(g_vec, vec, g_depth, depth)
        flat_results.append((res, depth))
        flat_scores.append(res["similarityBps"])

    # Results
    threshold = similarity_engine.min_similarity_bps
    gen_pass_rate = sum(s >= threshold for s in genuine_scores) / len(genuine_scores) * 100
    imp_rej_rate = sum(s < threshold for s in impostor_scores) / len(impostor_scores) * 100
    flat_gate_rej_rate = sum(not res["branches"]["flatPrintPassed"] for res, _ in flat_results) / len(flat_results) * 100
    flat_score_rej_rate = sum(s < threshold for s in flat_scores) / len(flat_scores) * 100
    flat_roughness = [f"{dp['relief_roughness']:.3f}mm" for _, dp in flat_results]

    print("=" * 60)
    print("ARTHENTIC SURFACE MATCHING CALIBRATION RESULTS")
    print("=" * 60)
    print(f"Threshold: {threshold} bps ({threshold/100:.1f}%)\n")

    print(f"Genuine Scores (Same surface):      {[f'{s/100:.1f}%' for s in genuine_scores]}")
    print(f"  Mean: {np.mean(genuine_scores)/100:.1f}% | Min: {np.min(genuine_scores)/100:.1f}% | Pass Rate: {gen_pass_rate:.0f}%")

    print(f"\nImpostor Scores (Different surface): {[f'{s/100:.1f}%' for s in impostor_scores]}")
    print(f"  Mean: {np.mean(impostor_scores)/100:.1f}% | Max: {np.max(impostor_scores)/100:.1f}% | Rejection Rate: {imp_rej_rate:.0f}%")

    print(f"\nFlat-Print Attack Scores:            {[f'{s/100:.1f}%' for s in flat_scores]}")
    print(f"  Relief Roughness:                  {flat_roughness} (Weave threshold >= 0.200mm)")
    print(f"  Mean: {np.mean(flat_scores)/100:.1f}% | Max: {np.max(flat_scores)/100:.1f}% | Score Rejection Rate: {flat_score_rej_rate:.0f}%")
    print(f"  Flatness Gate Rejection Rate:       {flat_gate_rej_rate:.0f}% (flatPrintPassed=False)")
    print("=" * 60)

    # Programmatic criteria verification
    all_passed = (
        gen_pass_rate == 100 and
        imp_rej_rate == 100 and
        flat_gate_rej_rate == 100 and
        flat_score_rej_rate == 100
    )
    if not all_passed:
        print("CALIBRATION BENCHMARK FAILED: Acceptance criteria not satisfied.")
        if exit_on_completion:
            sys.exit(1)
        return False

    print("CALIBRATION BENCHMARK SUCCESS: All criteria verified.")
    if exit_on_completion:
        sys.exit(0)
    return True

if __name__ == "__main__":
    run_calibration(exit_on_completion=True)

