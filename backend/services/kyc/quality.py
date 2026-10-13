"""Image quality gate — runs before OCR results are trusted."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

MIN_SIDE_WARN = 480
MIN_SIDE_FAIL = 240
BLUR_WARN = 60.0
BLUR_FAIL = 12.0
BRIGHT_MIN, BRIGHT_MAX = 50.0, 215.0
GLARE_FRACTION_WARN = 0.06


@dataclass
class QualityReport:
    ok: bool = True
    unusable: bool = False
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def assess_quality(img: np.ndarray) -> QualityReport:
    report = QualityReport()
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

    # Sharpness measured at a fixed scale so large and small uploads are comparable
    scale = 800.0 / max(h, w)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    blur = float(cv2.Laplacian(small, cv2.CV_64F).var())
    brightness = float(gray.mean())
    glare = float((gray > 250).mean())
    report.metrics = {"min_side": float(min(h, w)), "sharpness": round(blur, 1),
                      "brightness": round(brightness, 1), "glare_fraction": round(glare, 3)}

    if min(h, w) < MIN_SIDE_FAIL:
        report.unusable = True
        report.issues.append(f"resolution too low ({w}x{h})")
    elif min(h, w) < MIN_SIDE_WARN:
        report.issues.append(f"low resolution ({w}x{h})")
    if blur < BLUR_FAIL:
        report.unusable = True
        report.issues.append("image is too blurry to read")
    elif blur < BLUR_WARN:
        report.issues.append("image is slightly blurry")
    if brightness < BRIGHT_MIN:
        report.issues.append("image is too dark")
    elif brightness > BRIGHT_MAX:
        report.issues.append("image is overexposed")
    if glare > GLARE_FRACTION_WARN:
        report.issues.append("strong glare on the document")

    report.ok = not report.issues
    return report
