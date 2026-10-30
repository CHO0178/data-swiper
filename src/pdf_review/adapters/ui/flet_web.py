import asyncio
import base64
import os

import flet as ft

from pdf_review.application import ReviewApplication, ReviewSession
from pdf_review.domain import ClassificationLabel
from pdf_review.ports import PageRenderer


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
        page.padding = 12
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
        self.page_index = 0
        self.png: bytes | None = None
        self.error: str | None = None
        self.save_error: str | None = None
        self.busy = False
        self.zoomed = False
        self.swipe_dx = 0.0
        self.viewer_dx = 0.0
        self.viewer_dy = 0.0
        self.viewer_multitouch = False
        self.viewer: ft.InteractiveViewer | None = None

    def _show(self) -> None:
        summary = self.session.summary
        controls: list[ft.Control] = [
            ft.Text("PDF review", size=24, weight=ft.FontWeight.BOLD),
            ft.Text(f"Hotovo {summary.left + summary.right} / {summary.total} · 0: {summary.left} · 1: {summary.right}"),
        ]
        document = self.session.current
        if document is None:
            message = (
                "Složka neobsahuje žádná PDF." if summary.total == 0 else
                "Všechny dokumenty jsou zpracované." if summary.unreviewed == 0 else
                "Na konci seznamu zbývají nerozhodnuté dokumenty."
            )
            controls.extend([
                ft.Text(message, size=18),
                ft.Text(f"Celkem: {summary.total} · 0: {summary.left} · 1: {summary.right} · Nezpracované: {summary.unreviewed}"),
                ft.Button("Předchozí dokument", on_click=self._previous, disabled=summary.total == 0),
                ft.Button("Znovu projít nerozhodnuté", on_click=self._restart, disabled=summary.unreviewed == 0),
            ])
        else:
            controls.append(ft.Text(document.display_name, size=18, weight=ft.FontWeight.BOLD))
            controls.append(ft.Text(document.filename, size=12, color=ft.Colors.GREY_700))
            existing = self.session.results.get(document.filename)
            if existing is not None:
                controls.append(ft.Text(f"Uložené rozhodnutí: {int(existing)} · změna přepíše tento výsledek"))
            if self.save_error:
                controls.append(ft.Text(self.save_error, color=ft.Colors.RED))
            if self.error:
                controls.extend([
                    ft.Text(f"Chyba dokumentu: {self.error}", color=ft.Colors.RED),
                    ft.Row(controls=[
                        ft.Button("Zkusit znovu", on_click=self._retry),
                        ft.Button("Přeskočit bez rozhodnutí", on_click=self._skip),
                        ft.Button("Předchozí dokument", on_click=self._previous, disabled=self.session.index == 0),
                    ], wrap=True),
                ])
            elif self.png is None:
                controls.append(ft.ProgressRing())
            else:
                width = max(200, (self.page.width or 400) - 24)
                height = max(300, min(720, (self.page.height or 800) - 330))
                self.viewer = ft.InteractiveViewer(
                    content=ft.Image(
                        src=base64.b64encode(self.png).decode("ascii"),
                        width=width, height=height, fit=ft.BoxFit.CONTAIN,
                        error_content=ft.Text("Náhled stránky se nepodařilo zobrazit."),
                    ),
                    width=width, height=height, min_scale=1, max_scale=4,
                    interaction_update_interval=16,
                    on_interaction_start=self._interaction_start,
                    on_interaction_update=self._interaction_update,
                    on_interaction_end=self._interaction_end,
                )
                controls.extend([
                    ft.Row(controls=[
                        ft.Button("◀ Stránka", on_click=self._previous_page, disabled=self.page_index == 0),
                        ft.Text(f"{self.page_index + 1} / {self.page_count}"),
                        ft.Button("Stránka ▶", on_click=self._next_page, disabled=self.page_index >= self.page_count - 1),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("Přejeď po PDF vlevo pro 0, vpravo pro 1. Při přiblížení tah posouvá obraz."),
                    self.viewer,
                    ft.Row(controls=[
                        ft.Button("Přiblížit", on_click=self._zoom_in),
                        ft.Button("Oddálit", on_click=self._zoom_out),
                        ft.Button("Obnovit zoom", on_click=self._reset_zoom),
                        ft.Button("Vyšší kvalita" if self.dpi == self.default_dpi else "Běžná kvalita",
                                  on_click=self._toggle_quality),
                    ], wrap=True),
                    ft.GestureDetector(
                        content=ft.Container(content=ft.Text("Náhradní gesto: vlevo 0 / vpravo 1", text_align=ft.TextAlign.CENTER),
                                             padding=16, bgcolor=ft.Colors.BLUE_50, width=width),
                        on_horizontal_drag_start=self._swipe_start,
                        on_horizontal_drag_update=self._swipe_update,
                        on_horizontal_drag_end=self._swipe_end,
                    ),
                    ft.Row(controls=[
                        ft.Button("← 0", on_click=self._classify_left, disabled=self.busy),
                        ft.Button("1 →", on_click=self._classify_right, disabled=self.busy),
                    ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                    ft.Row(controls=[
                        ft.Button("Předchozí dokument", on_click=self._previous, disabled=self.session.index == 0),
                        ft.Button("Další nerozhodnutý", on_click=self._skip),
                    ], wrap=True),
                ])
        self.page.controls = [ft.SafeArea(content=ft.Column(controls=controls, scroll=ft.ScrollMode.AUTO, expand=True))]
        self.page.update()

    async def load_document(self) -> None:
        self.content = None
        self.png = None
        self.error = None
        self.save_error = None
        self.page_count = 0
        self.page_index = 0
        self.dpi = self.default_dpi
        self.zoomed = False
        self.viewer = None
        self._show()
        if self.session.current is None:
            return
        try:
            self.content = await asyncio.to_thread(self.session.read_current)
            self.page_count = await asyncio.to_thread(self.renderer.page_count, self.content)
            await self.render_page()
        except Exception as exc:
            self.error = str(exc)
            self._show()

    async def render_page(self) -> None:
        if self.content is None:
            return
        self.png = None
        self.error = None
        self.zoomed = False
        self._show()
        try:
            self.png = await asyncio.to_thread(self.renderer.render_page, self.content, self.page_index, self.dpi)
        except Exception as exc:
            self.error = str(exc)
        self._show()

    async def _classify(self, label: ClassificationLabel) -> None:
        if self.busy or self.error or self.png is None:
            return
        self.busy = True
        self._show()
        try:
            await asyncio.to_thread(self.session.classify, label)
        except Exception as exc:
            self.save_error = f"Uložení selhalo: {exc}"
            self._show()
        else:
            await self.load_document()
        finally:
            self.busy = False
            self._show()

    async def _classify_left(self, event: ft.Event) -> None:
        await self._classify(ClassificationLabel.LEFT)

    async def _classify_right(self, event: ft.Event) -> None:
        await self._classify(ClassificationLabel.RIGHT)

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

    async def _previous_page(self, event: ft.Event) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            await self.render_page()

    async def _next_page(self, event: ft.Event) -> None:
        if self.page_index + 1 < self.page_count:
            self.page_index += 1
            await self.render_page()

    def _interaction_start(self, event: ft.ScaleStartEvent) -> None:
        self.viewer_dx = 0.0
        self.viewer_dy = 0.0
        self.viewer_multitouch = event.pointer_count > 1

    def _interaction_update(self, event: ft.ScaleUpdateEvent) -> None:
        if event.pointer_count > 1 or abs(event.scale - 1) > 0.03:
            self.zoomed = True
            self.viewer_multitouch = True
            return
        if not self.zoomed and not self.viewer_multitouch:
            self.viewer_dx += event.focal_point_delta.x
            self.viewer_dy += event.focal_point_delta.y

    async def _interaction_end(self, event: ft.ScaleEndEvent) -> None:
        dx, dy = self.viewer_dx, self.viewer_dy
        self.viewer_dx = self.viewer_dy = 0.0
        if self.zoomed or self.viewer_multitouch or abs(dx) < 90 or abs(dx) < abs(dy) * 1.5:
            return
        await self._classify(ClassificationLabel.RIGHT if dx > 0 else ClassificationLabel.LEFT)

    async def _zoom_in(self, event: ft.Event) -> None:
        if self.viewer:
            await self.viewer.zoom(1.5)
            self.zoomed = True

    async def _zoom_out(self, event: ft.Event) -> None:
        if self.viewer:
            await self.viewer.zoom(0.67)
            # Conservative: only explicit reset enables swipe again.
            self.zoomed = True

    async def _reset_zoom(self, event: ft.Event) -> None:
        if self.viewer:
            await self.viewer.reset()
            self.zoomed = False

    async def _toggle_quality(self, event: ft.Event) -> None:
        self.dpi = 200 if self.dpi == self.default_dpi else self.default_dpi
        await self.render_page()

    def _swipe_start(self, event: ft.DragStartEvent) -> None:
        self.swipe_dx = 0.0

    def _swipe_update(self, event: ft.DragUpdateEvent) -> None:
        self.swipe_dx += event.primary_delta or 0.0

    async def _swipe_end(self, event: ft.DragEndEvent) -> None:
        distance = self.swipe_dx
        self.swipe_dx = 0.0
        if self.zoomed or abs(distance) < 90:
            return
        await self._classify(ClassificationLabel.RIGHT if distance > 0 else ClassificationLabel.LEFT)
