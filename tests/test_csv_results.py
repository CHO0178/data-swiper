import csv

import pytest

from pdf_review.adapters.storage import CsvResultStore
from pdf_review.domain import ClassificationLabel


def test_csv_utf8_upsert_and_preservation(tmp_path):
    path = tmp_path / "nested" / "results.csv"
    store = CsvResultStore(path)
    store.upsert("věda, číslo.pdf", ClassificationLabel.LEFT)
    store.upsert("sub/foto.pdf", ClassificationLabel.RIGHT)
    store.upsert("věda, číslo.pdf", ClassificationLabel.RIGHT)
    with path.open(encoding="utf-8", newline="") as file:
        assert list(csv.reader(file)) == [
            ["filename", "label"], ["věda, číslo.pdf", "1"], ["sub/foto.pdf", "1"]
        ]
    assert store.load()["věda, číslo.pdf"] == ClassificationLabel.RIGHT


@pytest.mark.parametrize("content", ["bad,header\na.pdf,0\n", "filename,label\na.pdf,2\n", "filename,label\na.pdf,0\na.pdf,1\n"])
def test_invalid_csv_preserved(tmp_path, content):
    path = tmp_path / "results.csv"
    path.write_text(content, encoding="utf-8")
    store = CsvResultStore(path)
    with pytest.raises(ValueError):
        store.upsert("b.pdf", ClassificationLabel.RIGHT)
    assert path.read_text(encoding="utf-8") == content


def test_replace_failure_keeps_previous_csv(tmp_path, monkeypatch):
    path = tmp_path / "results.csv"
    store = CsvResultStore(path)
    store.upsert("a.pdf", ClassificationLabel.LEFT)
    original = path.read_bytes()
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr("pdf_review.adapters.storage.csv_results.os.replace", fail)
    with pytest.raises(OSError):
        store.upsert("b.pdf", ClassificationLabel.RIGHT)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
