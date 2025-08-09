import shutil
import pytest
from PIL import Image, ImageDraw, ImageFont
import pytesseract

@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_pytesseract_recognizes_fraction():
    img = Image.new("L", (200, 80), color=255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("DejaVuSans.ttf", 40)
    draw.text((10, 10), "96/108", font=font, fill=0)
    text = pytesseract.image_to_string(
        img,
        config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ/-",
    )
    assert text.strip() == "96/108"
