#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append-only JSON log for send_all.py.

Each line in send_log.jsonl is one send attempt. We use JSON Lines rather than
a single JSON array so a crash mid-write can't corrupt past records.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "send_log.jsonl"
SCREENSHOT_DIR = LOG_DIR / "screenshots"
JST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def append(record: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": _now_iso(), **record}
    with LOG_FILE.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_all() -> list[dict[str, Any]]:
    if not LOG_FILE.exists():
        return []
    out = []
    with LOG_FILE.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def successful_names(message_yaml: str) -> set[str]:
    """Names that already have a success entry for this template."""
    return {
        r["municipality"]
        for r in load_all()
        if r.get("result") == "success"
        and r.get("message_yaml") == message_yaml
        and not r.get("dry_run")
    }


def summary() -> dict[str, int]:
    counts: dict[str, int] = {"success": 0, "failure": 0, "skipped": 0, "dry_run": 0}
    for r in load_all():
        if r.get("dry_run"):
            counts["dry_run"] += 1
            continue
        res = r.get("result", "unknown")
        counts[res] = counts.get(res, 0) + 1
    return counts


def screenshot_path(name: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(JST).strftime("%Y%m%dT%H%M%S")
    safe = name.replace("/", "_").replace("\\", "_")
    return SCREENSHOT_DIR / f"{safe}_{ts}.png"
