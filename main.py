import os
from pathlib import Path

from pdf_review.adapters.renderers import PyMuPdfRenderer
from pdf_review.adapters.retrievers import FolderPdfRetriever
from pdf_review.adapters.storage import CsvResultStore
from pdf_review.adapters.ui import FletWebUI
from pdf_review.application import ReviewApplication


def main() -> None:
    retriever = FolderPdfRetriever(
        root=Path(os.environ.get("PDF_REVIEW_DOCUMENTS", "documents")),
        recursive=os.environ.get("PDF_REVIEW_RECURSIVE", "false").lower() == "true",
    )
    results = CsvResultStore(Path(os.environ.get("PDF_REVIEW_RESULTS", "results/results.csv")))
    app = ReviewApplication(retriever, results)
    FletWebUI(renderer=PyMuPdfRenderer()).run(app)


if __name__ == "__main__":
    main()
