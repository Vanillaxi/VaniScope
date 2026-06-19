from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from webscoper.schemas.browser import RiskSignal


async def detect_risks(page: Page) -> list[RiskSignal]:
    signals: list[RiskSignal] = []

    page_facts = await _collect_page_facts(page)
    password_count = int(page_facts.get("password_count", 0))
    email_or_username_count = int(page_facts.get("email_or_username_count", 0))
    captcha_detected = bool(page_facts.get("captcha_detected", False))
    payment_detected = bool(page_facts.get("payment_detected", False))

    if password_count > 0:
        signals.append(
            RiskSignal(
                risk_type="password",
                message="Page contains password input fields. Do not enter real credentials.",
                severity="high",
            )
        )

    if captcha_detected:
        signals.append(
            RiskSignal(
                risk_type="captcha",
                message="Page appears to contain CAPTCHA or human-verification content.",
                severity="high",
            )
        )

    if payment_detected:
        signals.append(
            RiskSignal(
                risk_type="payment",
                message="Page appears to contain payment-related fields or text.",
                severity="high",
            )
        )

    if password_count > 0 and email_or_username_count > 0:
        signals.append(
            RiskSignal(
                risk_type="login",
                message="Page appears to contain a login form.",
                severity="medium",
            )
        )

    return signals


async def _collect_page_facts(page: Page) -> dict[str, Any]:
    try:
        result = await page.evaluate(
            """() => {
                const text = (document.body?.innerText || '').toLowerCase();
                const inputs = Array.from(document.querySelectorAll('input'));
                const iframes = Array.from(document.querySelectorAll('iframe'));

                const attrText = (el) => [
                    el.getAttribute('type'),
                    el.getAttribute('name'),
                    el.getAttribute('id'),
                    el.getAttribute('autocomplete'),
                    el.getAttribute('placeholder'),
                    el.getAttribute('aria-label'),
                    el.getAttribute('title')
                ].filter(Boolean).join(' ').toLowerCase();

                const iframeText = iframes.map(attrText).join(' ');
                const allInputText = inputs.map(attrText).join(' ');
                const combined = [text, iframeText, allInputText].join(' ');

                const hasAny = (needles) => needles.some((needle) => combined.includes(needle));

                const passwordCount = inputs.filter((input) =>
                    (input.getAttribute('type') || '').toLowerCase() === 'password'
                ).length;

                const emailOrUsernameCount = inputs.filter((input) => {
                    const data = attrText(input);
                    return data.includes('email') || data.includes('username') || data.includes('user name');
                }).length;

                return {
                    password_count: passwordCount,
                    email_or_username_count: emailOrUsernameCount,
                    captcha_detected: hasAny(['captcha', 'recaptcha', 'hcaptcha', 'verify you are human']),
                    payment_detected: hasAny(['card number', 'credit card', 'cvv', 'cvc', 'expiry', 'expiration date'])
                };
            }"""
        )
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    return {
        "password_count": 0,
        "email_or_username_count": 0,
        "captcha_detected": False,
        "payment_detected": False,
    }
