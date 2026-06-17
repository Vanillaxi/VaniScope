from __future__ import annotations

from types import TracebackType
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


class BrowserSession:
    def __init__(
        self,
        headless: bool = True,
        viewport: dict[str, int] | None = None,
    ) -> None:
        self.headless = headless
        self.viewport = viewport or {"width": 1440, "height": 900}
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> Page:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(viewport=self.viewport)
        self.page = await self._context.new_page()
        return self.page

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._close_quietly()

    async def _close_quietly(self) -> None:
        close_targets: list[Any] = [self._context, self._browser]
        for target in close_targets:
            if target is None:
                continue
            try:
                await target.close()
            except Exception:
                pass

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
