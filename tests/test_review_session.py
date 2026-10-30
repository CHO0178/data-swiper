import pytest

from pdf_review.application import ReviewApplication
from pdf_review.domain import ClassificationLabel, ReviewDocument


class FakeDocumentRetriever:
    def __init__(self, names: list[str]) -> None:
        self.documents = [ReviewDocument(name, name, name) for name in names]

    def list_documents(self) -> list[ReviewDocument]:
        return self.documents

    def read_document(self, document_id: str) -> bytes:
        if document_id == "broken.pdf":
            raise OSError("unreadable")
        return b"pdf"


class InMemoryResultStore:
    def __init__(self, initial=None, fail=False) -> None:
        self.results = dict(initial or {})
        self.fail = fail

    def load(self):
        return dict(self.results)

    def upsert(self, filename, label):
        if self.fail:
            raise OSError("write failed")
        self.results[filename] = label


def test_classification_resume_and_correction():
    retriever = FakeDocumentRetriever(["c.pdf", "a.pdf", "b.pdf"])
    store = InMemoryResultStore()
    app = ReviewApplication(retriever, store)
    session = app.new_session()
    assert session.current.filename == "a.pdf"
    session.classify(ClassificationLabel.LEFT)
    assert session.current.filename == "b.pdf"
    session.classify(ClassificationLabel.RIGHT)
    assert (session.summary.total, session.summary.left, session.summary.right, session.summary.unreviewed) == (3, 1, 1, 1)
    resumed = app.new_session()
    assert resumed.current.filename == "c.pdf"
    resumed.previous()
    assert resumed.current.filename == "b.pdf"
    resumed.classify(ClassificationLabel.LEFT)
    assert store.results == {"a.pdf": ClassificationLabel.LEFT, "b.pdf": ClassificationLabel.LEFT}
    assert resumed.current.filename == "c.pdf"


def test_empty_error_skip_and_failed_write():
    assert ReviewApplication(FakeDocumentRetriever([]), InMemoryResultStore()).new_session().summary.total == 0
    retriever = FakeDocumentRetriever(["broken.pdf", "good.pdf"])
    store = InMemoryResultStore(fail=True)
    session = ReviewApplication(retriever, store).new_session()
    with pytest.raises(OSError):
        session.read_current()
    with pytest.raises(OSError):
        session.classify(ClassificationLabel.RIGHT)
    assert session.current.filename == "broken.pdf"
    assert store.results == {}
    session.next_unreviewed()
    assert session.current.filename == "good.pdf"
    session.next_unreviewed()
    assert session.current is None
    assert session.summary.unreviewed == 2
    assert session.restart_unreviewed().filename == "broken.pdf"


def test_duplicate_filename_rejected():
    retriever = FakeDocumentRetriever(["a.pdf", "a.pdf"])
    with pytest.raises(ValueError, match="unique"):
        ReviewApplication(retriever, InMemoryResultStore()).new_session()
