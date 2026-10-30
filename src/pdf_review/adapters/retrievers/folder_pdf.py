from pathlib import Path

from pdf_review.domain import ReviewDocument


class FolderPdfRetriever:
    def __init__(self, root: Path, recursive: bool = False) -> None:
        self.root = root.resolve()
        self.recursive = recursive

    def list_documents(self) -> list[ReviewDocument]:
        if not self.root.is_dir():
            raise FileNotFoundError(f"Document folder does not exist: {self.root}")
        paths = self.root.rglob("*") if self.recursive else self.root.iterdir()
        filenames = sorted(
            path.relative_to(self.root).as_posix()
            for path in paths
            if path.is_file() and path.suffix.lower() == ".pdf" and not path.is_symlink()
        )
        return [
            ReviewDocument(id=name, filename=name, display_name=Path(name).name)
            for name in filenames
        ]

    def read_document(self, document_id: str) -> bytes:
        # Recheck membership for each read, so a client-supplied ID cannot open a path.
        if document_id not in {doc.id for doc in self.list_documents()}:
            raise ValueError(f"Unknown document ID: {document_id}")
        path = (self.root / document_id).resolve(strict=True)
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("Document path escaped the configured folder")
        return path.read_bytes()
