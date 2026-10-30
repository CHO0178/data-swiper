from pdf_review.application.review_session import ReviewSession
from pdf_review.ports import DocumentRetriever, ResultStore


class ReviewApplication:
    def __init__(self, retriever: DocumentRetriever, result_store: ResultStore) -> None:
        self.retriever = retriever
        self.result_store = result_store

    def new_session(self) -> ReviewSession:
        documents = sorted(self.retriever.list_documents(), key=lambda doc: doc.filename)
        ids = [document.id for document in documents]
        names = [document.filename for document in documents]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("Document IDs and CSV filenames must be unique")
        if any(not name or name.startswith("/") for name in names):
            raise ValueError("Invalid document filename")
        return ReviewSession(documents, self.retriever, self.result_store)
