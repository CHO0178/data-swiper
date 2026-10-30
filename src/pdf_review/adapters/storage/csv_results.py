import csv
import os
import tempfile
import threading
from pathlib import Path

from pdf_review.domain import ClassificationLabel


class CsvResultStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = threading.RLock()

    def load(self) -> dict[str, ClassificationLabel]:
        with self._lock:
            if not self.file_path.exists():
                return {}
            with self.file_path.open("r", encoding="utf-8", newline="") as file:
                reader = csv.reader(file)
                if next(reader, None) != ["filename", "label"]:
                    raise ValueError("Invalid CSV header; expected filename,label")
                results: dict[str, ClassificationLabel] = {}
                for row in reader:
                    if len(row) != 2 or not row[0] or row[1] not in ("0", "1"):
                        raise ValueError(f"Invalid CSV row: {row!r}")
                    if row[0] in results:
                        raise ValueError(f"Duplicate CSV filename: {row[0]}")
                    results[row[0]] = ClassificationLabel(int(row[1]))
                return results

    def upsert(self, filename: str, label: ClassificationLabel) -> None:
        if not filename or not isinstance(label, ClassificationLabel):
            raise ValueError("Invalid filename or label")
        with self._lock:
            results = self.load()
            results[filename] = label
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="", dir=self.file_path.parent,
                    prefix=f".{self.file_path.name}.", suffix=".tmp", delete=False,
                ) as file:
                    temporary_path = Path(file.name)
                    writer = csv.writer(file)
                    writer.writerow(["filename", "label"])
                    for name, value in results.items():
                        writer.writerow([name, int(value)])
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary_path, self.file_path)
                temporary_path = None
                if hasattr(os, "O_DIRECTORY"):
                    directory_fd = os.open(self.file_path.parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
