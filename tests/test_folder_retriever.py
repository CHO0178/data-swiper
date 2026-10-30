import pytest

from pdf_review.adapters.retrievers import FolderPdfRetriever
from pdf_review.adapters.storage import CsvResultStore
from pdf_review.application import ReviewApplication
from pdf_review.domain import ClassificationLabel


def test_recursive_relative_names_and_safe_read(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    (tmp_path / "one" / "same.pdf").write_bytes(b"one")
    (tmp_path / "two" / "same.pdf").write_bytes(b"two")
    retriever = FolderPdfRetriever(tmp_path, recursive=True)
    assert [doc.filename for doc in retriever.list_documents()] == ["one/same.pdf", "two/same.pdf"]
    assert retriever.read_document("two/same.pdf") == b"two"
    results = CsvResultStore(tmp_path / "results.csv")
    session = ReviewApplication(retriever, results).new_session()
    session.classify(ClassificationLabel.LEFT)
    session.classify(ClassificationLabel.RIGHT)
    assert results.load() == {
        "one/same.pdf": ClassificationLabel.LEFT,
        "two/same.pdf": ClassificationLabel.RIGHT,
    }
    with pytest.raises(ValueError):
        retriever.read_document("../outside.pdf")


def test_non_recursive_and_missing_root(tmp_path):
    (tmp_path / "inside").mkdir()
    (tmp_path / "inside" / "nested.pdf").write_bytes(b"nested")
    assert FolderPdfRetriever(tmp_path).list_documents() == []
    with pytest.raises(FileNotFoundError):
        FolderPdfRetriever(tmp_path / "missing").list_documents()
