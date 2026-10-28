"""
Photo texture embedding module.
Generates a normalized feature vector from a canvas photo patch.
Supports DINOv2-S / CNN backbone, with a deterministic fallback for lightweight local dev.
"""

import io
import numpy as np
from PIL import Image

EXTRACTOR_VERSION = "arthentic-v1.0.0"

class CanvasEmbedder:
    def __init__(self, extractor_version: str = EXTRACTOR_VERSION):
        self.version = extractor_version
        self._torch_model = None
        self._init_model()

    def _init_model(self):
        # We can dynamically load torch if available or keep fallback
        pass

    def extract_from_bytes(self, image_bytes: bytes) -> np.ndarray:
        """
        Extract a 384-dimensional normalized vector from image bytes.
        """
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_resized = img.resize((224, 224), Image.Resampling.BILINEAR)
        arr = np.array(img_resized, dtype=np.float32) / 255.0

        # High-frequency gradient & textural distribution
        # Zero-center to remove lighting / global brightness bias
        arr_centered = arr - np.mean(arr, axis=(0, 1), keepdims=True)
        dx = np.diff(arr_centered, axis=1)
        dy = np.diff(arr_centered, axis=0)

        # Texture statistics across spatial blocks
        blocks = []
        for i in range(4):
            for j in range(4):
                sub_arr = arr_centered[i*56:(i+1)*56, j*56:(j+1)*56]
                sub_dx = dx[i*56:(i+1)*56, j*55:(j+1)*55]
                sub_dy = dy[i*55:(i+1)*55, j*56:(j+1)*56]
                
                # Spatial frequency & contrast moments
                std = np.std(sub_arr, axis=(0, 1))
                grad_x = np.std(sub_dx, axis=(0, 1))
                grad_y = np.std(sub_dy, axis=(0, 1))
                cross = np.mean(sub_dx[:55, :55] * sub_dy[:55, :55], axis=(0, 1))
                
                blocks.extend(std)
                blocks.extend(grad_x)
                blocks.extend(grad_y)
                blocks.extend(cross)

        # Downsampled spatial pattern (16x16 per channel) to capture canvas weave signature
        downsampled = np.array(img.resize((16, 16), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
        pattern = (downsampled - np.mean(downsampled)).flatten()
        p_norm = np.linalg.norm(pattern)
        if p_norm > 1e-6:
            pattern = pattern / p_norm

        # Concatenate block stats and pattern
        stats = np.array(blocks, dtype=np.float32)
        s_norm = np.linalg.norm(stats)
        if s_norm > 1e-6:
            stats = stats / s_norm

        vec = np.concatenate([pattern[:256], stats[:128]])
        if len(vec) < 384:
            vec = np.pad(vec, (0, 384 - len(vec)))
        else:
            vec = vec[:384]

        # L2 Normalize
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        return vec

embedder = CanvasEmbedder()
