import asyncio
import base64
import os

import flet as ft

from pdf_review.application import ReviewApplication, ReviewSession
from pdf_review.domain import ClassificationLabel
from pdf_review.ports import PageRenderer

BASE_SCALE = 1.0
MAX_SCALE = 4.0
RESET_SCALE_THRESHOLD = 1.08


class FletWebUI:
    def __init__(self, renderer: PageRenderer, dpi: int = 150) -> None:
        self.renderer = renderer
        self.dpi = dpi

    def run(self, app: ReviewApplication) -> None:
        async def start_page(page: ft.Page) -> None:
            await self._serve(page, app)

        ft.run(
            start_page,
            view=ft.AppView.WEB_BROWSER,
            host=os.environ.get("PDF_REVIEW_HOST", "127.0.0.1"),
            port=int(os.environ.get("PDF_REVIEW_PORT", "8000")),
        )

    async def _serve(self, page: ft.Page, app: ReviewApplication) -> None:
        page.title = "PDF review"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 4
        try:
            session = await asyncio.to_thread(app.new_session)
        except Exception as exc:
            page.add(ft.Text(f"Cannot start review: {exc}", color=ft.Colors.RED))
            return
        controller = _ReviewPage(page, session, self.renderer, self.dpi)
        await controller.load_document()


class _ReviewPage:
    """State for one Flet browser connection."""

    def __init__(self, page: ft.Page, session: ReviewSession, renderer: PageRenderer, dpi: int) -> None:
        self.page = page
        self.session = session
        self.renderer = renderer
        self.default_dpi = dpi
        self.dpi = dpi
        self.content: bytes | None = None
        self.page_count = 0
        self.png_pages: list[bytes] = []
        self.error: str | None = None
        self.save_error: str | None = None
        self.busy = False
        self.load_generation = 0
        self.zoomed = False
        self.current_scale = BASE_SCALE
        self.gesture_start_scale = BASE_SCALE
        self.viewer_dx = 0.0
        self.viewer_dy = 0.0
        self.viewer_multitouch = False
        self.viewers: list[ft.InteractiveViewer] = []

    def _show(self) -> None:
        summary = self.session.summary
        document = self.session.current
        header = ft.Row(controls=[
            ft.Button("← Zpět", on_click=self._previous,
                      disabled=self.session.index == 0 or self.busy),
            ft.Text(document.display_name if document else "Hotovo", expand=True,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(f"{summary.left + summary.right}/{summary.total}"),
        ])
        body: list[ft.Control] = []
        self.viewers = []
        if document is None:
            message = (
                "Složka neobsahuje žádná PDF." if summary.total == 0 else
                "Všechny dokumenty jsou zpracované." if summary.unreviewed == 0 else
                "Na konci seznamu zbývají nerozhodnuté dokumenty."
            )
            body.extend([
                ft.Text(message, size=18),
                ft.Text(f"Celkem: {summary.total} · 0: {summary.left} · 1: {summary.right} · Nezpracované: {summary.unreviewed}"),
                ft.Button("Znovu projít nerozhodnuté", on_click=self._restart,
                          disabled=summary.unreviewed == 0),
            ])
        else:
            existing = self.session.results.get(document.filename)
            if existing is not None:
                body.append(ft.Text(f"Uložené rozhodnutí: {int(existing)} · změna přepíše tento výsledek"))
            if self.save_error:
                body.append(ft.Text(self.save_error, color=ft.Colors.RED))
            if self.error:
                body.extend([
                    ft.Text(f"Chyba dokumentu: {self.error}", color=ft.Colors.RED),
                    ft.Row(controls=[
                        ft.Button("Zkusit znovu", on_click=self._retry),
                        ft.Button("Přeskočit bez rozhodnutí", on_click=self._skip),
                    ], wrap=True),
                ])
            else:
                width = max(200, (self.page.width or 400) - 8)
                height = max(300, (self.page.height or 800) - 80)
                page_controls: list[ft.Control] = []
                for png in self.png_pages:
                    page_controls.append(ft.Image(
                        src=base64.b64encode(png).decode("ascii"),
                        width=width, height=height, fit=ft.BoxFit.CONTAIN,
                        error_content=ft.Text("Náhled stránky se nepodařilo zobrazit."),
                    ))
                if page_controls:
                    viewer = ft.InteractiveViewer(
                        content=ft.Column(
                            controls=page_controls,
                            width=width,
                            height=len(self.png_pages) * height + max(0, len(self.png_pages) - 1) * 8,
                            spacing=8,
                        ),
                        width=width, expand=True,
                        min_scale=BASE_SCALE, max_scale=MAX_SCALE,
                        constrained=False,
                        interaction_update_interval=16,
                        on_interaction_start=self._interaction_start,
                        on_interaction_update=self._interaction_update,
                        on_interaction_end=self._interaction_end,
                    )
                    self.viewers.append(viewer)
                    body.append(viewer)
                if self.page_count == 0 or len(self.png_pages) < self.page_count:
                    body.append(ft.ProgressRing())
        self.page.controls = [ft.SafeArea(content=ft.Column(controls=[
            header,
            ft.Column(controls=body, expand=True),
        ], expand=True), expand=True)]
        self.page.update()

    async def load_document(self) -> None:
        self.load_generation += 1
        generation = self.load_generation
        self.content = None
        self.png_pages = []
        self.error = None
        self.save_error = None
        self.page_count = 0
        self.dpi = self.default_dpi
        self.zoomed = False
        self.current_scale = BASE_SCALE
        self.gesture_start_scale = BASE_SCALE
        self._show()
        if self.session.current is None:
            return
        try:
            content = await asyncio.to_thread(self.session.read_current)
            if generation != self.load_generation:
                return
            count = await asyncio.to_thread(self.renderer.page_count, content)
            if generation != self.load_generation:
                return
            self.content = content
            self.page_count = count
            await self.render_pages()
        except Exception as exc:
            if generation == self.load_generation:
                self.error = str(exc)
                self._show()

    async def render_pages(self) -> None:
        if self.content is None:
            return
        generation = self.load_generation
        self.png_pages = []
        self.error = None
        self.zoomed = False
        self.current_scale = BASE_SCALE
        self.gesture_start_scale = BASE_SCALE
        self._show()
        for index in range(self.page_count):
            try:
                png = await asyncio.to_thread(
                    self.renderer.render_page, self.content, index, self.dpi
                )
            except Exception as exc:
                if generation == self.load_generation:
                    self.error = str(exc)
                    self._show()
                return
            if generation != self.load_generation:
                return
            self.png_pages.append(png)
            self._show()

    async def _classify(self, label: ClassificationLabel) -> None:
        if (self.busy or self.error or self.page_count == 0
                or len(self.png_pages) != self.page_count):
            return
        self.busy = True
        self._show()
        try:
            await asyncio.to_thread(self.session.classify, label)
        except Exception as exc:
            self.save_error = f"Uložení selhalo: {exc}"
            self.current_scale = BASE_SCALE
            self.zoomed = False
            self._show()
        else:
            await self.load_document()
        finally:
            self.busy = False
            self._show()

    async def _previous(self, event: ft.Event) -> None:
        self.session.previous()
        await self.load_document()

    async def _skip(self, event: ft.Event) -> None:
        self.session.next_unreviewed()
        await self.load_document()

    async def _retry(self, event: ft.Event) -> None:
        await self.load_document()

    async def _restart(self, event: ft.Event) -> None:
        self.session.restart_unreviewed()
        await self.load_document()

    def _interaction_start(self, event: ft.ScaleStartEvent) -> None:
        self.viewer_dx = 0.0
        self.viewer_dy = 0.0
        self.viewer_multitouch = event.pointer_count > 1
        self.gesture_start_scale = self.current_scale

    def _interaction_update(self, event: ft.ScaleUpdateEvent) -> None:
        if event.pointer_count > 1:
            self.viewer_multitouch = True
            self.current_scale = max(
                BASE_SCALE,
                min(MAX_SCALE, self.gesture_start_scale * event.scale),
            )
            self.zoomed = self.current_scale > RESET_SCALE_THRESHOLD
            return
        if self.viewer_multitouch:
            return
        if not self.zoomed and not self.viewer_multitouch:
            self.viewer_dx += event.focal_point_delta.x
            self.viewer_dy += event.focal_point_delta.y

    async def _interaction_end(self, event: ft.ScaleEndEvent) -> None:
        dx, dy = self.viewer_dx, self.viewer_dy
        self.viewer_dx = self.viewer_dy = 0.0
        if self.viewer_multitouch and self.current_scale <= RESET_SCALE_THRESHOLD:
            for viewer in self.viewers:
                await viewer.reset()
            self.current_scale = BASE_SCALE
            self.zoomed = False
        if self.zoomed or self.viewer_multitouch or abs(dx) < 90 or abs(dx) < abs(dy) * 1.5:
            return
        await self._classify(ClassificationLabel.RIGHT if dx > 0 else ClassificationLabel.LEFT)
