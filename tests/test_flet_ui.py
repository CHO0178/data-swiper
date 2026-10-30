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


class TwoPageRenderer(Renderer):
    def page_count(self, content):
        return 2

    def render_page(self, content, page_index, dpi):
        return f"png-{page_index}".encode()


def test_review_screen_builds_with_installed_flet_api():
    page = FakePage()
    session = ReviewApplication(Retriever(), Store()).new_session()
    controller = _ReviewPage(page, session, renderer=None, dpi=150)
    controller.png_pages = [b"png"]
    controller.page_count = 1
    controller._show()
    assert len(controller.viewers) == 1
    assert controller.viewers[0].content.controls[0].src == base64.b64encode(b"png").decode("ascii")
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
        assert controller.png_pages == [b"png"]
        await controller._classify(ClassificationLabel.LEFT)
        assert store.results == {"a.pdf": ClassificationLabel.LEFT}
        assert session.current.filename == "b.pdf"
        assert controller.png_pages == [b"png"]
    asyncio.run(scenario())


def test_pages_share_viewer_without_outer_scroll():
    async def scenario():
        page = FakePage()
        session = ReviewApplication(Retriever(), Store()).new_session()
        controller = _ReviewPage(page, session, TwoPageRenderer(), 150)
        await controller.load_document()
        root = page.controls[0].content
        header, document_body = root.controls
        assert header.controls[0].content == "← Zpět"
        assert header.controls[0].disabled is True
        assert header.controls[1].value == "a.pdf"
        assert document_body.scroll is None
        assert len(controller.viewers) == 1
        viewer = controller.viewers[0]
        assert viewer.constrained is False
        assert viewer.expand is True
        assert viewer.height is None
        assert viewer.content.height > page.height
        assert sum(control.__class__.__name__ == "Image" for control in viewer.content.controls) == 2
        assert viewer.content.controls[0].height >= page.height - 80
        assert all(control.__class__.__name__ != "Button" for control in document_body.controls)

        await controller._classify(ClassificationLabel.LEFT)
        assert page.controls[0].content.controls[0].controls[0].disabled is False
        await controller._classify(ClassificationLabel.RIGHT)
        assert session.current is None
        assert page.controls[0].content.controls[0].controls[0].disabled is False
        await controller._previous(None)
        assert session.current.filename == "b.pdf"

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
    resets = []

    class Viewer:
        async def reset(self):
            resets.append(True)

    controller.viewers = [Viewer()]

    async def record(label):
        classified.append(label)

    controller._classify = record

    async def gesture(dx, dy=0, pointers=1, scale=1):
        controller._interaction_start(SimpleNamespace(pointer_count=pointers))
        controller._interaction_update(SimpleNamespace(
            pointer_count=pointers, scale=scale,
            focal_point_delta=SimpleNamespace(x=dx, y=dy),
        ))
        await controller._interaction_end(SimpleNamespace())

    async def scenario():
        await gesture(-110)
        await gesture(120)
        await gesture(40)
        await gesture(100, 100)
        await gesture(120, pointers=2, scale=2)
        assert controller.zoomed is True
        await gesture(120)
        assert classified == [ClassificationLabel.LEFT, ClassificationLabel.RIGHT]
        await gesture(120, pointers=2, scale=0.5)
        assert controller.current_scale == 1
        assert controller.zoomed is False
        assert len(resets) == 1
        await gesture(120)
        assert classified == [ClassificationLabel.LEFT, ClassificationLabel.RIGHT,
                              ClassificationLabel.RIGHT]

    asyncio.run(scenario())
