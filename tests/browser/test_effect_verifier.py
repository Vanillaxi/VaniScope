from __future__ import annotations

import pytest

from webscoper.browser.effects import EffectVerifier
from webscoper.browser.session import BrowserSession
from webscoper.schemas.browser import ExpectedEffect


@pytest.mark.asyncio
async def test_effect_verifier_waits_for_delayed_content() -> None:
    async with BrowserSession() as page:
        await page.set_content(
            """
            <!doctype html>
            <html>
            <body>
              <button onclick="setTimeout(() => {
                document.getElementById('result').style.display = 'block'
              }, 500)">Load</button>
              <section id="result" style="display:none">Delayed content ready</section>
            </body>
            </html>
            """
        )
        body_text_before = await page.locator("body").inner_text()
        await page.get_by_role("button", name="Load").click()

        result = await EffectVerifier().verify(
            page,
            expected=ExpectedEffect(
                type="content_appears",
                value="Delayed content ready",
            ),
            url_before=page.url,
            body_text_before=body_text_before,
            timeout_ms=1500,
        )

    assert result.satisfied is True
    assert result.status == "success"
