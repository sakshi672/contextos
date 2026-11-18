"""Bounded OCR helpers shared by image and scanned-PDF extraction."""

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from rapidocr import RapidOCR
import pypdfium2 as pdfium

from .extract_text import PermanentExtractionError

MAX_PIXELS = 20_000_000
MAX_SIDE = 4000
MAX_PDF_OCR_PAGES = 40
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@lru_cache(maxsize=1)
def engine():
    return RapidOCR()


def recognize_image(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as original:
            image = ImageOps.exif_transpose(original)
            image.load()
            if image.width * image.height > MAX_PIXELS:
                raise PermanentExtractionError("image_pixel_limit")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            output = BytesIO()
            image.convert("RGB").save(output, format="PNG")
        result = engine()(output.getvalue())
        return "\n".join(result.txts or ())
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise PermanentExtractionError("invalid_image") from exc


def recognize_pdf_page(document, page_index: int) -> str:
    page = document[page_index]
    try:
        width, height = page.get_size()
        scale = min(2, (MAX_PIXELS / max(width * height, 1)) ** 0.5)
        if scale < 0.5:
            raise PermanentExtractionError("pdf_page_pixel_limit")
        bitmap = page.render(scale=scale)
        try:
            result = engine()(bitmap.to_numpy())
            return "\n".join(result.txts or ())
        finally:
            bitmap.close()
    except (ValueError, OSError, RuntimeError) as exc:
        raise PermanentExtractionError("pdf_render_failed") from exc
    finally:
        page.close()


def open_pdf(source: bytes):
    try:
        return pdfium.PdfDocument(source)
    except (ValueError, OSError, RuntimeError) as exc:
        raise PermanentExtractionError("pdf_render_failed") from exc
