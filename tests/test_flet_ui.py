import asyncio
import base64
import inspect
from types import SimpleNamespace

from pdf_review.adapters.ui.flet_web import FletWebUI, _ReviewPage
from pdf_review.application import ReviewApplication
from pdf_review.domain import ClassificationLabel, ReviewDocument


class FakePage:
    width = 390
    height = 800

    def __init__(self):
        self.controls = []
        self.updates = 0

    def update(self):
        self.updates += 1


class Retriever:
    def list_documents(self):
        return [ReviewDocument("a", "a.pdf", "a.pdf"), ReviewDocument("b", "b.pdf", "b.pdf")]

    def read_document(self, document_id):
        return b"pdf"


class Store:
    def __init__(self):
        self.results = {}

    def load(self):
        return dict(self.results)

    def upsert(self, filename, label):
        self.results[filename] = label


class Renderer:
    def page_count(self, content):
        return 1

    def render_page(self, content, page_index, dpi):
        return b"png"


def test_review_screen_builds_with_installed_flet_api():
    page = FakePage()
    session = ReviewApplication(Retriever(), Store()).new_session()
    controller = _ReviewPage(page, session, renderer=None, dpi=150)
    controller.png = b"png"
    controller.page_count = 1
    controller._show()
    assert controller.viewer is not None
    assert controller.viewer.content.src == base64.b64encode(b"png").decode("ascii")
    assert page.updates == 1
    controller.error = "damaged PDF"
    controller._show()
    assert page.updates == 2


def test_ui_action_saves_then_opens_next_document():
    async def scenario():
        page = FakePage()
        store = Store()
        session = ReviewApplication(Retriever(), store).new_session()
        controller = _ReviewPage(page, session, Renderer(), 150)
        await controller.load_document()
        assert controller.png == b"png"
        await controller._classify(ClassificationLabel.LEFT)
        assert store.results == {"a.pdf": ClassificationLabel.LEFT}
        assert session.current.filename == "b.pdf"
        assert controller.png == b"png"
    asyncio.run(scenario())


def test_flet_entrypoint_is_async(monkeypatch):
    captured = {}

    def fake_run(callback, **kwargs):
        captured["callback"] = callback

    monkeypatch.setattr("pdf_review.adapters.ui.flet_web.ft.run", fake_run)
    FletWebUI(Renderer()).run(ReviewApplication(Retriever(), Store()))
    assert inspect.iscoroutinefunction(captured["callback"])


def test_viewer_swipe_threshold_direction_and_zoom_guard():
    page = FakePage()
    session = ReviewApplication(Retriever(), Store()).new_session()
    controller = _ReviewPage(page, session, Renderer(), 150)
    classified = []

    async def record(label):
        classified.append(label)

    controller._classify = record

    async def gesture(dx, dy=0, pointers=1):
        controller._interaction_start(SimpleNamespace(pointer_count=pointers))
        controller._interaction_update(SimpleNamespace(
            pointer_count=pointers, scale=1,
            focal_point_delta=SimpleNamespace(x=dx, y=dy),
        ))
        await controller._interaction_end(SimpleNamespace())

    async def scenario():
        await gesture(-110)
        await gesture(120)
        await gesture(40)
        await gesture(100, 100)
        await gesture(120, pointers=2)
        assert classified == [ClassificationLabel.LEFT, ClassificationLabel.RIGHT]

    asyncio.run(scenario())
