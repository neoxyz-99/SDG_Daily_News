"""Decode artwork before treating a file as publishable."""
from io import BytesIO

from PIL import Image


def validate_jpeg(image_bytes: bytes) -> None:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format != "JPEG":
                raise ValueError("Expected JPEG artwork")
            image.verify()
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
    except Exception as exc:
        raise ValueError("Artwork is not a decodable JPEG") from exc
