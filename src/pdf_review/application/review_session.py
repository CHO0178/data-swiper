from dataclasses import dataclass

from pdf_review.domain import ClassificationLabel, ReviewDocument
from pdf_review.ports.retriever import DocumentRetriever
from pdf_review.ports.result_store import ResultStore


@dataclass(frozen=True)
class ReviewSummary:
    total: int
    left: int
    right: int
    unreviewed: int


class ReviewSession:
    def __init__(
        self,
        documents: list[ReviewDocument],
        retriever: DocumentRetriever,
        result_store: ResultStore,
    ) -> None:
        self.documents = tuple(documents)
        self.retriever = retriever
        self.result_store = result_store
        self.results = result_store.load()
        self.index = self._first_unreviewed(0)

    def _first_unreviewed(self, start: int) -> int:
        return next(
            (i for i in range(start, len(self.documents)) if self.documents[i].filename not in self.results),
            len(self.documents),
        )

    @property
    def current(self) -> ReviewDocument | None:
        return self.documents[self.index] if self.index < len(self.documents) else None

    @property
    def summary(self) -> ReviewSummary:
        labels = [self.results.get(document.filename) for document in self.documents]
        left = labels.count(ClassificationLabel.LEFT)
        right = labels.count(ClassificationLabel.RIGHT)
        return ReviewSummary(len(labels), left, right, len(labels) - left - right)

    def read_current(self) -> bytes:
        document = self.current
        if document is None:
            raise ValueError("No current document")
        return self.retriever.read_document(document.id)

    def classify(self, label: ClassificationLabel) -> None:
        document = self.current
        if document is None:
            raise ValueError("No current document")
        if not isinstance(label, ClassificationLabel):
            raise ValueError("Label must be LEFT or RIGHT")
        self.result_store.upsert(document.filename, label)
        self.results[document.filename] = label
        self.index = self._first_unreviewed(self.index + 1)

    def previous(self) -> ReviewDocument | None:
        if self.index > 0:
            self.index -= 1
        return self.current

    def next_unreviewed(self) -> ReviewDocument | None:
        self.index = self._first_unreviewed(self.index + 1)
        return self.current

    def restart_unreviewed(self) -> ReviewDocument | None:
        self.index = self._first_unreviewed(0)
        return self.current
