import pymupdf
import pytest

from pdf_review.adapters.renderers import PyMuPdfRenderer


@pytest.mark.parametrize("count", [1, 2])
def test_render_pages(count):
    document = pymupdf.open()
    for _ in range(count):
        document.new_page(width=200, height=300)
    content = document.tobytes()
    document.close()
    renderer = PyMuPdfRenderer()
    assert renderer.page_count(content) == count
    assert renderer.render_page(content, count - 1, 120).startswith(b"\x89PNG")
    with pytest.raises(IndexError):
        renderer.render_page(content, count, 120)
