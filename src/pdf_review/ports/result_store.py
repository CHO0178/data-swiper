from typing import Protocol

from pdf_review.domain import ClassificationLabel


class ResultStore(Protocol):
    def load(self) -> dict[str, ClassificationLabel]: ...

    def upsert(self, filename: str, label: ClassificationLabel) -> None: ...
