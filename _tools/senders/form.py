#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwright-based form sender used by send_all.py.

Fills each form by mapping the MD `フォームフィールド` canonical name to a
value sourced from the YAML template's `差出人` block + subject/body. If a
2-step submit button (e.g. `cmd:confirm`) is present, the sender clicks it
first and then looks for `cmd:submit` on the next page.

CAPTCHA-blocked municipalities are expected to be filtered out upstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from log_store import screenshot_path

FILL_TIMEOUT_MS = 15_000
NAV_TIMEOUT_MS = 30_000


@dataclass
class SendResult:
    ok: bool
    target: str
    error: str | None = None
    screenshot: str | None = None


def _value_for(field_name: str, municipality_name: str, subject: str,
               body: str, sender: dict[str, Any]) -> str | None:
    """Map canonical MD field name to a concrete value."""
    # sender['氏名'] etc. may be missing → default to empty
    m = {
        "名前": sender.get("氏名", ""),
        "フリガナ": sender.get("フリガナ", ""),  # optional in template
        "メールアドレス": sender.get("メール", ""),
        "メール確認": sender.get("メール", ""),
        "郵便番号": sender.get("郵便番号", ""),
        "都道府県": sender.get("都道府県", ""),
        "住所": sender.get("住所", ""),
        "住所2": sender.get("住所2", ""),
        "電話番号": sender.get("電話", ""),
        "件名": subject,
        "本文": body,
        "年齢": sender.get("年齢", ""),
        "性別": sender.get("性別", ""),
        "職業": sender.get("職業", ""),
    }
    return m.get(field_name)


def _fill_field(page, field, value: str) -> None:
    sel = field.selector
    if not sel:
        return
    try:
        if field.type == "textarea":
            page.fill(sel, value, timeout=FILL_TIMEOUT_MS)
        elif field.type == "select":
            # Best-effort: try label match, else first non-empty option
            try:
                page.select_option(sel, label=value, timeout=FILL_TIMEOUT_MS)
            except Exception:
                locator = page.locator(sel)
                options = locator.locator("option").all_text_contents()
                pick = next((o for o in options if o.strip()), None)
                if pick:
                    page.select_option(sel, label=pick, timeout=FILL_TIMEOUT_MS)
        elif field.type == "radio":
            # Pick first radio in the group — best effort only
            page.locator(sel).first.check(timeout=FILL_TIMEOUT_MS)
        elif field.type == "checkbox":
            page.locator(sel).first.check(timeout=FILL_TIMEOUT_MS)
        else:  # text / default
            page.fill(sel, value, timeout=FILL_TIMEOUT_MS)
    except Exception:
        # Swallow per-field errors so we still attempt submit; caller gets
        # failure via post-submit verification.
        pass


def _click_submit(page, fields) -> bool:
    """Detect and click the submit button. Return True if a 2-step flow is in play."""
    # First try: explicit 送信ボタン row in MD (the selector lives only if set)
    from playwright.sync_api import TimeoutError as PWTimeout  # noqa: PLC0415

    two_step = False
    confirm_names = ("cmd:confirm", "confirm")
    submit_candidates = [
        'button[name="cmd:confirm"]',
        'input[name="cmd:confirm"]',
        'button[type="submit"]',
        'input[type="submit"]',
    ]
    for sel in submit_candidates:
        btn = page.locator(sel)
        if btn.count() == 0:
            continue
        name = (btn.first.get_attribute("name") or "").lower()
        if any(c in name for c in confirm_names):
            two_step = True
        try:
            btn.first.click(timeout=FILL_TIMEOUT_MS)
            page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        except PWTimeout:
            pass
        break
    if two_step:
        # Look for final submit on the confirmation page
        for sel in (
            'button[name="cmd:submit"]',
            'input[name="cmd:submit"]',
            'button[type="submit"]',
            'input[type="submit"]',
        ):
            btn = page.locator(sel)
            if btn.count() == 0:
                continue
            try:
                btn.first.click(timeout=FILL_TIMEOUT_MS)
                page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
            except PWTimeout:
                pass
            break
    return two_step


_COMPLETION_WORDS = (
    "お問い合わせありがとう",
    "送信が完了",
    "送信しました",
    "受け付けました",
    "受付完了",
    "ありがとうございました",
    "thank you",
)


def _looks_completed(page) -> bool:
    try:
        body = page.inner_text("body", timeout=5_000).lower()
    except Exception:
        return False
    return any(w.lower() in body for w in _COMPLETION_WORDS)


def send(municipality, template: dict[str, Any], *, dry_run: bool = False,
         headless: bool = True) -> SendResult:
    url = municipality.form_url
    if not url:
        return SendResult(ok=False, target="", error="no_form_url_in_md")
    if not municipality.fields:
        return SendResult(ok=False, target=url, error="no_fields_in_md (要Playwright調査)")

    sender = template.get("差出人", {}) or {}
    subject = template.get("subject", "")
    body = template.get("body", "")

    # Render template vars
    for k, v in [
        ("{{自治体名}}", municipality.name),
        ("{{敬称}}", template.get("敬称", "ご担当者様")),
        ("{{差出人.氏名}}", sender.get("氏名", "")),
        ("{{差出人.住所}}", sender.get("住所", "")),
        ("{{差出人.電話}}", sender.get("電話", "")),
        ("{{差出人.メール}}", sender.get("メール", "")),
    ]:
        subject = subject.replace(k, str(v))
        body = body.replace(k, str(v))

    if dry_run:
        return SendResult(ok=True, target=url)

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    shot_path = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(url, timeout=NAV_TIMEOUT_MS)
            page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)

            for f in municipality.fields:
                val = _value_for(f.name, municipality.name, subject, body, sender)
                if val is None:
                    continue
                if f.type == "button":
                    continue
                _fill_field(page, f, val)

            _click_submit(page, municipality.fields)

            shot = screenshot_path(municipality.name)
            try:
                page.screenshot(path=str(shot), full_page=True)
                shot_path = str(shot)
            except Exception:
                pass

            if _looks_completed(page):
                return SendResult(ok=True, target=url, screenshot=shot_path)
            return SendResult(
                ok=False, target=url,
                error="completion_word_not_found (要目視確認)",
                screenshot=shot_path,
            )
        except Exception as e:  # noqa: BLE001
            try:
                shot = screenshot_path(municipality.name + "_ERR")
                page.screenshot(path=str(shot), full_page=True)
                shot_path = str(shot)
            except Exception:
                pass
            return SendResult(
                ok=False, target=url,
                error=f"{type(e).__name__}: {e}",
                screenshot=shot_path,
            )
        finally:
            context.close()
            browser.close()
