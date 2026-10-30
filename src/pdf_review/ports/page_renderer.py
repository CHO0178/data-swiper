from typing import Protocol


class PageRenderer(Protocol):
    def page_count(self, content: bytes) -> int: ...

    def render_page(self, content: bytes, page_index: int, dpi: int) -> bytes: ...
