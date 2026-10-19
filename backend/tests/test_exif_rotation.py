import asyncio
import io

from PIL import Image

from utils.image_processing import save_upload_bytes


def _jpeg_with_orientation(orientation: int) -> bytes:
    """A 200 wide × 100 high image stored with an EXIF orientation tag, like a phone photo."""
    im = Image.new("RGB", (200, 100), "white")
    exif = Image.Exif()
    exif[274] = orientation
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_exif_rotation_is_applied_to_uploads(tmp_path):
    # orientation 8 / 6 = stored sideways: the upright picture is 100 wide × 200 high
    for orientation in (6, 8):
        _, img = asyncio.run(save_upload_bytes(_jpeg_with_orientation(orientation), str(tmp_path), "id.jpg"))
        assert img.shape[:2] == (200, 100), orientation
    # no tag / normal orientation: unchanged
    _, img = asyncio.run(save_upload_bytes(_jpeg_with_orientation(1), str(tmp_path), "id.jpg"))
    assert img.shape[:2] == (100, 200)
