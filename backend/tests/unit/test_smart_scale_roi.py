import io

import pytest
from PIL import Image, ImageDraw

from services.recognition.roi import assess_crop_quality, crop_image_bytes, normalize_roi
from services.recognition.samples import canonical_roi_device_id


def _sample_image() -> bytes:
    image = Image.new("RGB", (800, 600), "#dbeafe")
    draw = ImageDraw.Draw(image)
    draw.rectangle((180, 120, 620, 500), fill="#64748b")
    draw.ellipse((270, 190, 520, 440), fill="#f59e0b")
    draw.line((180, 120, 620, 500), fill="#172554", width=12)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def test_normalize_roi_rejects_out_of_bounds_coordinates():
    with pytest.raises(ValueError, match="超出图片边界"):
        normalize_roi({"x": 0.8, "y": 0.2, "width": 0.3, "height": 0.4})


def test_crop_uses_normalized_coordinates_and_produces_training_image():
    result = crop_image_bytes(
        _sample_image(),
        {"x": 0.2, "y": 0.1, "width": 0.6, "height": 0.7, "rotation": 0},
    )
    assert result.width == 480
    assert result.height == 420
    assert result.quality_status == "passed"
    assert result.quality_score > 0
    assert Image.open(io.BytesIO(result.data)).size == (480, 420)


def test_flat_or_empty_crop_cannot_pass_quality_gate():
    image = Image.new("RGB", (320, 240), "#ffffff")
    status, score, reason = assess_crop_quality(image)
    assert status == "failed"
    assert score < 0.2
    assert reason


def test_all_uvc_sources_share_the_sohe_fixed_roi():
    assert canonical_roi_device_id("uvc") == "uvc-product-1"
    assert canonical_roi_device_id("uvc-product-2") == "uvc-product-1"
    assert canonical_roi_device_id("external-camera") == "external-camera"
