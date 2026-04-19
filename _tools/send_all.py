#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-send a templated message to every 自治体 MD.

Examples:
  # dry run first 5 of石狩地方
  python _tools/send_all.py --message _tools/messages/_template.yml \
      --dry-run --include-region 石狩地方 --limit 5

  # send emails only
  python _tools/send_all.py --message _tools/messages/shicho_mark.yml \
      --include-method email

  # resume after interruption
  python _tools/send_all.py --message _tools/messages/shicho_mark.yml --resume
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

# make `import md_parser` / `import log_store` work regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))

import log_store  # noqa: E402
from md_parser import Municipality, load_all  # noqa: E402


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="自治体一括送信スクリプト")
    ap.add_argument("--message", required=True, help="YAML テンプレートのパス")
    ap.add_argument("--dry-run", action="store_true",
                    help="実送信せず入力内容だけログに残す")
    ap.add_argument("--include-region", action="append", default=[],
                    help="振興局で絞り込み（複数指定可: 例 --include-region 石狩地方）")
    ap.add_argument("--include-method", action="append", default=[],
                    choices=["form", "email", "tel"],
                    help="連絡手段で絞り込み（複数指定可）")
    ap.add_argument("--only", default="",
                    help="自治体名でカンマ区切り指定（例: --only 札幌市,中札内村）")
    ap.add_argument("--resume", action="store_true",
                    help="同一テンプレで送信済みの自治体はスキップ")
    ap.add_argument("--limit", type=int, default=0,
                    help="最初のN件のみ処理（0=制限なし）")
    ap.add_argument("--interval", type=int, default=0,
                    help="送信間隔(秒)。既定=email 30s / form 60s。明示すると両方ともその値")
    ap.add_argument("--from-email", default="s.takahashi.hokkaido@gmail.com",
                    help="送信元メールアドレス（Gmail API認証済みアカウント）")
    ap.add_argument("--show-browser", action="store_true",
                    help="Playwright を非ヘッドレスで動かす（デバッグ用）")
    return ap.parse_args()


def load_template(path: str) -> dict:
    with open(path, encoding="utf-8") as fp:
        tpl = yaml.safe_load(fp)
    for required in ("subject", "body", "差出人"):
        if required not in tpl:
            raise SystemExit(f"テンプレートに {required} がありません: {path}")
    return tpl


def filter_targets(all_: list[Municipality], args, done: set[str]) -> list[Municipality]:
    regions = set(args.include_region)
    methods = set(args.include_method)
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    out = []
    for m in all_:
        if regions and m.region not in regions:
            continue
        if methods and m.method not in methods:
            continue
        if only and m.name not in only:
            continue
        if args.resume and m.name in done:
            continue
        out.append(m)
    if args.limit:
        out = out[: args.limit]
    return out


def interval_for(method: str, args) -> int:
    if args.interval:
        return args.interval
    return 30 if method == "email" else 60 if method == "form" else 0


def dispatch(m: Municipality, tpl: dict, args, template_name: str) -> str:
    """Process one municipality. Return the recorded result string."""
    base = {
        "municipality": m.name,
        "region": m.region,
        "method": m.method,
        "message_yaml": template_name,
        "dry_run": args.dry_run,
    }

    # Skip: tel / CAPTCHA / no digital target
    if m.method == "tel":
        log_store.append({**base, "result": "skipped", "reason": "no-digital-channel",
                          "target": None})
        return "skipped"
    if m.is_captcha_blocked:
        log_store.append({**base, "result": "skipped", "reason": f"captcha:{m.auto_send}",
                          "target": m.form_url})
        return "skipped"
    if m.method is None:
        log_store.append({**base, "result": "skipped", "reason": "no-method", "target": None})
        return "skipped"

    if m.method == "email":
        from senders.mail import send as send_mail  # noqa: PLC0415
        r = send_mail(m, tpl, dry_run=args.dry_run, from_email=args.from_email)
        log_store.append({
            **base,
            "target": r.target,
            "result": "success" if r.ok else "failure",
            "error": r.error,
            "message_id": r.message_id,
        })
        return "success" if r.ok else "failure"

    if m.method == "form":
        from senders.form import send as send_form  # noqa: PLC0415
        r = send_form(m, tpl, dry_run=args.dry_run, headless=not args.show_browser)
        log_store.append({
            **base,
            "target": r.target,
            "result": "success" if r.ok else "failure",
            "error": r.error,
            "screenshot": r.screenshot,
        })
        return "success" if r.ok else "failure"

    log_store.append({**base, "result": "skipped", "reason": f"unknown-method:{m.method}",
                      "target": None})
    return "skipped"


def main() -> int:
    args = parse_args()
    tpl_path = Path(args.message).resolve()
    tpl = load_template(str(tpl_path))
    template_name = tpl_path.name

    done = log_store.successful_names(template_name) if args.resume else set()

    all_records = load_all()
    targets = filter_targets(all_records, args, done)

    print(f"[send_all] template={template_name}  targets={len(targets)}/{len(all_records)}  dry_run={args.dry_run}")
    if args.resume:
        print(f"[send_all] resume skip count={len(done)}")

    counts: Counter[str] = Counter()
    for i, m in enumerate(targets, 1):
        label = f"[{i}/{len(targets)}] {m.region}/{m.name} ({m.method})"
        print(label, flush=True)
        try:
            res = dispatch(m, tpl, args, template_name)
        except KeyboardInterrupt:
            print("\n[send_all] interrupted — re-run with --resume to continue.")
            break
        except Exception as e:  # noqa: BLE001
            log_store.append({
                "municipality": m.name, "region": m.region, "method": m.method,
                "message_yaml": template_name, "dry_run": args.dry_run,
                "result": "failure", "error": f"UNCAUGHT {type(e).__name__}: {e}",
            })
            res = "failure"
        counts[res] += 1
        # Pause between real sends (not during dry-run)
        if not args.dry_run and i < len(targets):
            wait = interval_for(m.method, args)
            if wait:
                time.sleep(wait)

    print(f"\n[send_all] done: {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
