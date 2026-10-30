from typing import Protocol

from pdf_review.domain import ReviewDocument


class DocumentRetriever(Protocol):
    def list_documents(self) -> list[ReviewDocument]: ...

    def read_document(self, document_id: str) -> bytes: ...
