from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pdf_review.application import ReviewApplication


class ReviewUI(Protocol):
    def run(self, app: "ReviewApplication") -> None: ...
