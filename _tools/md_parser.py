#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse 自治体 MD files into dict records for send_all.py.

Reads every `北海道/{振興局}/{自治体名}.md` and returns a list of dicts with
the fields required by the senders: contact method, email, form URL, CAPTCHA
flag, auto-send verdict, form fields table.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
HOKKAIDO_DIR = ROOT / "北海道"


@dataclass
class FormField:
    name: str
    selector: str
    type: str  # text / textarea / select / radio / checkbox / button
    required: bool
    fixed: str | None = None


@dataclass
class Municipality:
    name: str
    region: str
    path: str  # relative to repo root, forward slashes
    method: str | None          # form / email / tel
    email: str | None
    form_url: str | None
    captcha_note: str | None    # 要対策（reCAPTCHA） 等、未設定なら None
    auto_send: str | None       # 可 / 不可 / 要対策(...) / 要Playwright
    fields: list[FormField] = field(default_factory=list)
    memo: str = ""

    @property
    def is_captcha_blocked(self) -> bool:
        return bool(self.auto_send) and self.auto_send.startswith("要対策")


_SETTING_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$")
_FIELD_TABLE_HEADER = re.compile(r"^\|\s*フィールド名\s*\|")
_FIELD_ROW = re.compile(
    r"^\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$"
)


def _extract_setting(lines: list[str], key: str) -> str | None:
    """Return the value for a 送信設定 row keyed by `key`, or None if missing/empty."""
    for line in lines:
        m = _SETTING_ROW.match(line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if k == key:
            v = v.strip()
            if not v or v == "-":
                return None
            return v
    return None


def _extract_contact_email(lines: list[str]) -> str | None:
    """Pull the メール row from ## 連絡先 — used when 連絡手段=email."""
    in_contact = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## 連絡先"):
            in_contact = True
            continue
        if in_contact and stripped.startswith("## "):
            break
        if not in_contact:
            continue
        m = _SETTING_ROW.match(line)
        if not m:
            continue
        if m.group(1) == "メール":
            v = m.group(2).strip()
            if not v or v.startswith("※"):
                return None
            return v
    return None


def _extract_fields(lines: list[str]) -> list[FormField]:
    fields: list[FormField] = []
    i = 0
    n = len(lines)
    while i < n:
        if _FIELD_TABLE_HEADER.match(lines[i]):
            # skip header + separator
            i += 2
            while i < n:
                line = lines[i]
                if not line.strip().startswith("|"):
                    break
                m = _FIELD_ROW.match(line)
                if m:
                    fname, selector, ftype, req, fixed = (g.strip() for g in m.groups())
                    if fname and fname != "送信ボタン" and not fname.startswith("(Playwright"):
                        fields.append(FormField(
                            name=fname,
                            selector=selector,
                            type=ftype or "text",
                            required=(req == "○"),
                            fixed=fixed or None,
                        ))
                i += 1
            break
        i += 1
    return fields


def _extract_memo(text: str) -> str:
    m = re.search(r"## メモ\s*\n(.*?)$", text, re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


def parse_md(path: Path) -> Municipality:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    name = lines[0].lstrip("# ").strip() if lines else path.stem
    region = path.parent.name

    method = _extract_setting(lines, "連絡手段")
    form_url = _extract_setting(lines, "フォームURL")
    captcha_note = _extract_setting(lines, "CAPTCHA")
    auto_send = _extract_setting(lines, "自動送信可否")

    email = None
    if method == "email":
        email = _extract_contact_email(lines)

    rel = path.relative_to(ROOT).as_posix()
    return Municipality(
        name=name,
        region=region,
        path=rel,
        method=method,
        email=email,
        form_url=form_url,
        captcha_note=captcha_note,
        auto_send=auto_send,
        fields=_extract_fields(lines),
        memo=_extract_memo(text),
    )


def iter_md_files() -> Iterable[Path]:
    for region_dir in sorted(HOKKAIDO_DIR.iterdir()):
        if not region_dir.is_dir():
            continue
        for md in sorted(region_dir.glob("*.md")):
            yield md


def load_all() -> list[Municipality]:
    return [parse_md(p) for p in iter_md_files()]


if __name__ == "__main__":
    # quick sanity check
    from collections import Counter
    records = load_all()
    by_method = Counter(r.method for r in records)
    captcha = sum(1 for r in records if r.is_captcha_blocked)
    print(f"total: {len(records)}")
    print(f"by method: {dict(by_method)}")
    print(f"CAPTCHA blocked: {captcha}")
    print("\nsample:")
    for r in records[:3]:
        print(f"  {r.region}/{r.name}: method={r.method} url={r.form_url} email={r.email} fields={len(r.fields)}")
