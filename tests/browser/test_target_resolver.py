from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from webscoper.browser.target import TargetResolver


@pytest.mark.asyncio
async def test_target_resolver_finds_button_by_hint() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.set_content("<button>Quickstart</button>")

            resolved = await TargetResolver().resolve(page, "Quickstart", ["button"])

            assert resolved.selected is not None
            assert resolved.confidence > 0
            assert resolved.selected.strategy in {"role_name", "text"}
            assert resolved.selected.visible is True
        finally:
            await context.close()
            await browser.close()
