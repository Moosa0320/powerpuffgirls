"""Photo utilities: resize, EXIF date extraction, and quality checking (guide section 9)."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from PIL import Image, ImageOps, ImageStat

MAX_DIM = 1280
JPEG_QUALITY = 82


def process_uploaded_image(raw_bytes: bytes) -> tuple[bytes, datetime | None, dict[str, Any]]:
    """Resizes raw image bytes to max 1280px JPEG, extracts EXIF date, and computes quality flags."""
    img = Image.open(io.BytesIO(raw_bytes))
    img = ImageOps.exif_transpose(img)

    # 1. Extract EXIF date if available
    taken_at: datetime | None = None
    try:
        exif = img.getexif()
        if exif:
            # 36867 = DateTimeOriginal, 306 = DateTime
            date_str = exif.get(36867) or exif.get(306)
            if date_str:
                taken_at = datetime.strptime(str(date_str).strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        taken_at = None

    # 2. Resize maintaining aspect ratio
    if img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    if max(width, height) > MAX_DIM:
        scale = MAX_DIM / max(width, height)
        new_w = max(1, int(width * scale))
        new_h = max(1, int(height * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Save to JPEG buffer
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    processed_bytes = buf.getvalue()

    # 3. Quality checks: brightness & blur
    stat = ImageStat.Stat(img)
    # Average luminance using standard formula (0.299 R + 0.587 G + 0.114 B)
    mean_rgb = stat.mean
    luminance = 0.299 * mean_rgb[0] + 0.587 * mean_rgb[1] + 0.114 * mean_rgb[2]

    is_dark = luminance < 45.0
    is_overexposed = luminance > 225.0

    # Blur estimation using Laplacian variance
    is_blur = False
    try:
        import numpy as np
        # Convert to grayscale
        gray = img.convert("L")
        arr = np.array(gray, dtype=np.float32)
        # Compute Laplacian kernel [[0, 1, 0], [1, -4, 1], [0, 1, 0]]
        laplacian = (
            np.roll(arr, 1, axis=0)
            + np.roll(arr, -1, axis=0)
            + np.roll(arr, 1, axis=1)
            + np.roll(arr, -1, axis=1)
            - 4 * arr
        )
        # Trim boundaries
        var = float(laplacian[1:-1, 1:-1].var())
        is_blur = var < 65.0
    except Exception:
        is_blur = False

    retake_prompts: list[str] = []
    if is_blur:
        retake_prompts.append("The photo is blurry. Please hold the phone steady and tap to focus.")
    if is_dark:
        retake_prompts.append("The photo is too dark. Please take it in better light or daylight.")
    if is_overexposed:
        retake_prompts.append("The photo is overexposed or has direct flash glare. Try shielding the leaf.")

    quality_flags = {
        "blur": is_blur,
        "dark": is_dark,
        "overexposed": is_overexposed,
        "luminance": round(luminance, 1),
        "guidance_adherence": "3-shot guidance: 1) whole plant, 2) close-up leaf, 3) wide field",
        "retake_prompt": " ".join(retake_prompts) if retake_prompts else None,
    }

    return processed_bytes, taken_at, quality_flags
