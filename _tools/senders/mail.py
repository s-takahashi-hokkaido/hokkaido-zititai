#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gmail API sender used by send_all.py.

Uses OAuth user credentials (desktop app flow). On first run the user is
taken through a browser consent screen; the resulting token is cached and
refreshed automatically on subsequent runs.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CRED_DIR = Path(__file__).resolve().parent.parent / "credentials"
CLIENT_SECRET = CRED_DIR / "gmail_oauth.json"
TOKEN_FILE = CRED_DIR / "gmail_token.json"


@dataclass
class SendResult:
    ok: bool
    target: str
    error: str | None = None
    message_id: str | None = None


def _get_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CLIENT_SECRET.exists():
            raise FileNotFoundError(
                f"Gmail OAuth client secret not found at {CLIENT_SECRET}. "
                "See _tools/credentials/README.md for setup."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _build_service():
    return build("gmail", "v1", credentials=_get_credentials(), cache_discovery=False)


def _render(template_text: str, municipality_name: str, tpl: dict[str, Any]) -> str:
    sender = tpl.get("差出人", {}) or {}
    replacements = {
        "{{自治体名}}": municipality_name,
        "{{敬称}}": tpl.get("敬称", "ご担当者様"),
        "{{差出人.氏名}}": sender.get("氏名", ""),
        "{{差出人.住所}}": sender.get("住所", ""),
        "{{差出人.電話}}": sender.get("電話", ""),
        "{{差出人.メール}}": sender.get("メール", ""),
    }
    out = template_text
    for k, v in replacements.items():
        out = out.replace(k, str(v))
    return out


def build_message(municipality_name: str, to_email: str, tpl: dict[str, Any],
                  from_email: str) -> tuple[str, str, str | None]:
    """Return (rendered_subject, rendered_body_text, rendered_body_html or None)."""
    subject = _render(tpl.get("subject", ""), municipality_name, tpl)
    body_text = _render(tpl.get("body", ""), municipality_name, tpl)
    body_html = tpl.get("body_html")
    if body_html:
        body_html = _render(body_html, municipality_name, tpl)
    return subject, body_text, body_html


def _encode_mime(from_email: str, to_email: str, subject: str,
                 body_text: str, body_html: str | None) -> dict:
    if body_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    else:
        msg = MIMEText(body_text, "plain", "utf-8")
    msg["To"] = to_email
    msg["From"] = from_email
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw}


def send(municipality, template: dict[str, Any], *, dry_run: bool = False,
         from_email: str = "s.takahashi.hokkaido@gmail.com") -> SendResult:
    to_email = municipality.email
    if not to_email:
        return SendResult(ok=False, target="", error="no_email_in_md")
    subject, body_text, body_html = build_message(
        municipality.name, to_email, template, from_email
    )
    if dry_run:
        return SendResult(ok=True, target=to_email, error=None, message_id="DRY_RUN")
    service = _build_service()
    payload = _encode_mime(from_email, to_email, subject, body_text, body_html)
    try:
        sent = service.users().messages().send(userId="me", body=payload).execute()
        return SendResult(ok=True, target=to_email, message_id=sent.get("id"))
    except Exception as e:  # noqa: BLE001 — we want to record any failure
        return SendResult(ok=False, target=to_email, error=f"{type(e).__name__}: {e}")
