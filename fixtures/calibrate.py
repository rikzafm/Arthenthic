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
import numpy as np
from server.ml.embedder import embedder
from server.ml.depth_features import depth_extractor
from server.ml.similarity import similarity_engine

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))

def run_calibration():
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
    genuine_scores = []
    for i in range(2, 6):
        with open(os.path.join(FIXTURES_DIR, f"canvas_sample_{i}.jpg"), "rb") as f:
            photo = f.read()
        with open(os.path.join(FIXTURES_DIR, f"depth_sample_{i}.bin"), "rb") as f:
            depth_bytes = f.read()

        vec = embedder.extract_from_bytes(photo)
        depth = depth_extractor.extract_features(depth_bytes, intrinsics)
        res = similarity_engine.compare(g_vec, vec, g_depth, depth)
        genuine_scores.append(res["similarityBps"])

    # 3. Test impostor samples (different surfaces)
    impostor_scores = []
    for i in range(1, 4):
        with open(os.path.join(FIXTURES_DIR, f"different_surface_{i}.jpg"), "rb") as f:
            photo = f.read()
        with open(os.path.join(FIXTURES_DIR, f"different_depth_{i}.bin"), "rb") as f:
            depth_bytes = f.read()

        vec = embedder.extract_from_bytes(photo)
        depth = depth_extractor.extract_features(depth_bytes, intrinsics)
        res = similarity_engine.compare(g_vec, vec, g_depth, depth)
        impostor_scores.append(res["similarityBps"])

    # 4. Test flat-print attacks
    flat_scores = []
    for i in range(1, 3):
        with open(os.path.join(FIXTURES_DIR, f"flat_print_{i}.jpg"), "rb") as f:
            photo = f.read()
        with open(os.path.join(FIXTURES_DIR, f"flat_print_depth_{i}.bin"), "rb") as f:
            depth_bytes = f.read()

        vec = embedder.extract_from_bytes(photo)
        depth = depth_extractor.extract_features(depth_bytes, intrinsics)
        res = similarity_engine.compare(g_vec, vec, g_depth, depth)
        flat_scores.append(res["similarityBps"])

    # Results
    threshold = similarity_engine.min_similarity_bps
    print("=" * 60)
    print("ARTHENTIC SURFACE MATCHING CALIBRATION RESULTS")
    print("=" * 60)
    print(f"Threshold: {threshold} bps ({threshold/100:.1f}%)\n")

    print(f"Genuine Scores (Same surface):      {[f'{s/100:.1f}%' for s in genuine_scores]}")
    print(f"  Mean: {np.mean(genuine_scores)/100:.1f}% | Min: {np.min(genuine_scores)/100:.1f}% | Pass Rate: {sum(s >= threshold for s in genuine_scores)/len(genuine_scores)*100:.0f}%")

    print(f"\nImpostor Scores (Different surface): {[f'{s/100:.1f}%' for s in impostor_scores]}")
    print(f"  Mean: {np.mean(impostor_scores)/100:.1f}% | Max: {np.max(impostor_scores)/100:.1f}% | Rejection Rate: {sum(s < threshold for s in impostor_scores)/len(impostor_scores)*100:.0f}%")

    print(f"\nFlat-Print Attack Scores:            {[f'{s/100:.1f}%' for s in flat_scores]}")
    print(f"  Mean: {np.mean(flat_scores)/100:.1f}% | Max: {np.max(flat_scores)/100:.1f}% | Rejection Rate: {sum(s < threshold for s in flat_scores)/len(flat_scores)*100:.0f}%")
    print("=" * 60)

if __name__ == "__main__":
    run_calibration()

