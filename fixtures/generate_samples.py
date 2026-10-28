"""
Generate synthetic sample capture fixtures for calibration and testing.
Simulates:
1. Physical canvas captures (rough surface relief, micro-texture)
2. Different artwork canvas captures
3. Flat-print paper attack captures (minimal depth relief variance)
"""

import os
import json
import numpy as np
from PIL import Image

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))

def create_synthetic_captures():
    os.makedirs(FIXTURES_DIR, exist_ok=True)

    intrinsics = {
        "fx": 1420.5,
        "fy": 1420.5,
        "cx": 960.0,
        "cy": 720.0
    }

    with open(os.path.join(FIXTURES_DIR, "intrinsics.json"), "w") as f:
        json.dump(intrinsics, f, indent=2)

    # 1. Authentic canvas: Base surface texture (Elena Vance - Study in Blue and Gold)
    np.random.seed(42)
    base_tex = np.random.randint(100, 220, (224, 224, 3), dtype=np.uint8)

    # Generate 5 repeats with small natural noise
    for i in range(1, 6):
        noise = np.random.normal(0, 4, (224, 224, 3)).astype(np.int16)
        patch = np.clip(base_tex.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(patch)
        img.save(os.path.join(FIXTURES_DIR, f"canvas_sample_{i}.jpg"))

        # Depth buffer with natural canvas weave relief (std dev ~ 0.45mm)
        z = np.full((128, 128), 0.14, dtype=np.float32)
        relief = np.random.normal(0, 0.00045, (128, 128)).astype(np.float32)
        depth = z + relief
        depth.tofile(os.path.join(FIXTURES_DIR, f"depth_sample_{i}.bin"))

    # 2. Different canvas surface (Attack / Negative control)
    diff_tex = np.random.randint(40, 150, (224, 224, 3), dtype=np.uint8)
    for i in range(1, 4):
        noise = np.random.normal(0, 5, (224, 224, 3)).astype(np.int16)
        patch = np.clip(diff_tex.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(patch)
        img.save(os.path.join(FIXTURES_DIR, f"different_surface_{i}.jpg"))

        depth = np.full((128, 128), 0.14, dtype=np.float32) + np.random.normal(0, 0.0004, (128, 128)).astype(np.float32)
        depth.tofile(os.path.join(FIXTURES_DIR, f"different_depth_{i}.bin"))

    # 3. Flat print attack (Photo of canvas printed on paper - near zero depth relief)
    for i in range(1, 3):
        patch = np.clip(base_tex.astype(np.int16) + np.random.normal(0, 6, (224, 224, 3)), 0, 255).astype(np.uint8)
        img = Image.fromarray(patch)
        img.save(os.path.join(FIXTURES_DIR, f"flat_print_{i}.jpg"))

        # Perfectly flat plane, std dev < 0.1mm (flat print detection should catch this)
        flat_depth = np.full((128, 128), 0.14, dtype=np.float32) + np.random.normal(0, 0.00008, (128, 128)).astype(np.float32)
        flat_depth.tofile(os.path.join(FIXTURES_DIR, f"flat_print_depth_{i}.bin"))

    print(f"Generated test fixtures in {FIXTURES_DIR}")

if __name__ == "__main__":
    create_synthetic_captures()

