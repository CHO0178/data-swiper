import pymupdf


class PyMuPdfRenderer:
    def __init__(self, max_pixels: int = 12_000_000) -> None:
        self.max_pixels = max_pixels

    def page_count(self, content: bytes) -> int:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise ValueError("Password-protected PDF is unsupported")
            if document.page_count == 0:
                raise ValueError("PDF has no pages")
            return document.page_count

    def render_page(self, content: bytes, page_index: int, dpi: int) -> bytes:
        if not 72 <= dpi <= 220:
            raise ValueError("DPI must be between 72 and 220")
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise ValueError("Password-protected PDF is unsupported")
            if not 0 <= page_index < document.page_count:
                raise IndexError("PDF page index is out of range")
            page = document[page_index]
            scale = dpi / 72
            if page.rect.width * page.rect.height * scale * scale > self.max_pixels:
                raise ValueError("PDF page exceeds the rendered image size limit")
            return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
