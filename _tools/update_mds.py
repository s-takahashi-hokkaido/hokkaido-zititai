#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate MD updates from labels.json + survey.json.
Outputs:
  - フォームフィールド table with selectors, types, required marks
  - 自動送信可否 value (可 / 要対策(CAPTCHA) / 要Playwright)
  - Preserves existing メモ, adds technical notes if needed
Run with --apply to write changes; default is --dry-run.
"""
import os, re, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Semantic mapping from label text → canonical field name
LABEL_MAP = [
    (re.compile(r"フリガナ|ふりがな|カナ|かな", re.I), "フリガナ"),
    (re.compile(r"e[-\s]?mail|メールアドレス|メール|mail", re.I), "メールアドレス"),  # careful ordering
    (re.compile(r"氏名|お名前|名前|ご氏名|ご担当者", re.I), "名前"),
    (re.compile(r"確認用|もう一度|再入力|確認のため", re.I), "メール確認"),
    (re.compile(r"郵便番号|〒", re.I), "郵便番号"),
    (re.compile(r"都道府県", re.I), "都道府県"),
    (re.compile(r"住所|所在地|ご住所", re.I), "住所"),
    (re.compile(r"電話番号|TEL|tel|ご連絡先", re.I), "電話番号"),
    (re.compile(r"件名|タイトル|題名|subject", re.I), "件名"),
    (re.compile(r"返信方法|回答方法|連絡方法|ご希望の連絡", re.I), "返信方法"),
    (re.compile(r"性別", re.I), "性別"),
    (re.compile(r"年齢|お歳", re.I), "年齢"),
    (re.compile(r"職業|ご職業", re.I), "職業"),
    (re.compile(r"部署|担当課|担当部署|送信先|宛先", re.I), "送信先部署"),
    (re.compile(r"区分|種別|カテゴリ|分類|お問い合わせ種別", re.I), "カテゴリ"),
    (re.compile(r"内容|本文|要件|質問|お問い合わせ内容|ご意見|ご要望|ご質問|メッセージ|message|inquiry", re.I), "本文"),
    (re.compile(r"同意|プライバシーポリシー|個人情報", re.I), "同意"),
]

# Fallback mapping from field name
NAME_MAP = [
    (re.compile(r"kana|kn|furigana", re.I), "フリガナ"),
    (re.compile(r"email|e[-_]?mail|mail", re.I), "メールアドレス"),
    (re.compile(r"name", re.I), "名前"),
    (re.compile(r"conf", re.I), "メール確認"),
    (re.compile(r"zip|post", re.I), "郵便番号"),
    (re.compile(r"pref|prefec", re.I), "都道府県"),
    (re.compile(r"addr|address", re.I), "住所"),
    (re.compile(r"tel|phone", re.I), "電話番号"),
    (re.compile(r"title|subject", re.I), "件名"),
    (re.compile(r"reply|answer_method", re.I), "返信方法"),
    (re.compile(r"gender|sex", re.I), "性別"),
    (re.compile(r"age", re.I), "年齢"),
    (re.compile(r"job|career|occupation", re.I), "職業"),
    (re.compile(r"dept|section|department", re.I), "送信先部署"),
    (re.compile(r"category|type|kind", re.I), "カテゴリ"),
    (re.compile(r"comment|body|text|content|message|opinion|inquiry", re.I), "本文"),
]

def canonical_name(label, name):
    """Return canonical Japanese field name for the given label and name."""
    for pat, canon in LABEL_MAP:
        if pat.search(label):
            return canon
    for pat, canon in NAME_MAP:
        if pat.search(name):
            return canon
    return None

def build_field_table(record):
    """Build the フォームフィールド table rows (list of strings)."""
    rows = ["| フィールド名 | セレクタ | 入力種別 | 必須 | 固定値 |",
            "|-------------|---------|---------|------|-------|"]
    seen_canon = {}
    fields = record.get("fields", [])
    submit_field = None
    for f in fields:
        ftype = f["type"]
        if ftype in ("reset","image"):
            continue
        if ftype == "submit":
            if not submit_field:
                submit_field = f
            continue
        if f.get("_dup_radio"):
            continue
        name = f["name"]
        label = f.get("label", "")
        canon = canonical_name(label, name)
        # Email confirmation heuristic: if canon already hit email and name has "2" or "conf"
        if canon == "メールアドレス" and seen_canon.get("メールアドレス", 0) >= 1:
            canon = "メール確認"
        if canon is None:
            canon = f"（未分類: {label[:20]}）" if label else f"（不明: {name}）"
        # avoid duplicate canonical name - suffix with (2), (3), ...
        if canon in seen_canon:
            seen_canon[canon] += 1
            canon = f"{canon}{seen_canon[canon]}"
        else:
            seen_canon[canon] = 1
        # selector: prefer id, fallback to name
        sel = f'[name="{name}"]' if name else ""
        if ftype == "select":
            input_type = "select"
        elif ftype == "textarea":
            input_type = "textarea"
        elif ftype == "radio":
            input_type = "radio"
        elif ftype == "checkbox":
            input_type = "checkbox"
        else:
            input_type = "text"
        req = "○" if f.get("required") else ""
        rows.append(f"| {canon} | {sel} | {input_type} | {req} | |")
    # submit button row
    if submit_field:
        sn = submit_field["name"]
        ss = f'[name="{sn}"]' if sn else ""
        rows.append(f"| 送信ボタン | {ss} | button | - | - |")
    else:
        rows.append("| 送信ボタン | | button | - | - |")
    return rows

def determine_auto_send(record, captcha):
    """Return (value_for_自動送信可否, メモ補足行 or None)."""
    if record.get("error") == "no_form":
        return "要Playwright", "静的GETではフォームHTMLが取得できず（JS描画またはCookie/セッション必須）。Playwrightでの自動化が必要。"
    if captcha:
        return f"要対策（{'/'.join(captcha)}）", f"CAPTCHA検出: {'/'.join(captcha)}。自動送信には外部CAPTCHA解決サービス等の対策要。"
    # 2-step confirm flow detection
    has_confirm = any((f.get("name","").lower() in ("cmd:confirm","confirm") or "confirm" in f.get("name","").lower()) for f in record.get("fields", []) if f.get("type")=="submit")
    note = None
    if has_confirm:
        note = "2段階送信（確認画面→送信ボタン）。Playwrightで `cmd:confirm` 押下後の `cmd:submit` 等の確定動作が必要。"
    return "可", note

def update_md(path, field_rows, auto_send, memo_add):
    full = os.path.join(ROOT, path)
    with open(full, encoding="utf-8") as fp:
        text = fp.read()
    original = text

    # Replace 自動送信可否
    text = re.sub(
        r"(\|\s*自動送信可否\s*\|)\s*[^\|]*\|",
        lambda m: f"{m.group(1)} {auto_send} |",
        text, count=1
    )

    # Replace フォームフィールド table (from ### フォームフィールド to next ## or end)
    pattern = re.compile(r"(### フォームフィールド\s*\n)(.*?)(?=\n## |\Z)", re.DOTALL)
    def repl_fields(m):
        header = m.group(1)
        new_body = "\n" + "\n".join(field_rows) + "\n\n"
        return header + new_body
    text = pattern.sub(repl_fields, text, count=1)

    # Append memo if provided (avoid duplication)
    if memo_add:
        # find ## メモ section
        mm = re.search(r"(## メモ\s*\n)", text)
        if mm and memo_add not in text:
            insert_pos = mm.end()
            text = text[:insert_pos] + "\n" + memo_add + "\n" + text[insert_pos:]

    changed = (text != original)
    return changed, text

def main():
    apply = "--apply" in sys.argv
    labels = json.load(open(os.path.join(ROOT, "_tools", "labels.json"), encoding="utf-8"))
    survey = json.load(open(os.path.join(ROOT, "_tools", "survey.json"), encoding="utf-8"))
    # Map url → captcha info from survey
    captcha_map = {r["url"]: r.get("captcha", []) for r in survey}

    changes = []
    for rec in labels:
        url = rec["url"]
        path = rec["path"]
        captcha = captcha_map.get(url, [])
        if rec.get("error"):
            # no-form case
            field_rows = ["| フィールド名 | セレクタ | 入力種別 | 必須 | 固定値 |",
                          "|-------------|---------|---------|------|-------|",
                          "| (Playwright調査で確定) | | | | |",
                          "| 送信ボタン | | button | - | - |"]
        else:
            field_rows = build_field_table(rec)
        auto_send, memo = determine_auto_send(rec, captcha)
        changed, new_text = update_md(path, field_rows, auto_send, memo)
        if changed:
            changes.append((path, auto_send, new_text))

    print(f"Will update {len(changes)} MD files")
    for path, auto_send, _ in changes[:20]:
        print(f"  {path}  [自動送信可否={auto_send}]")
    if len(changes) > 20:
        print(f"  ... and {len(changes)-20} more")

    if apply:
        for path, _, new_text in changes:
            full = os.path.join(ROOT, path)
            with open(full, "w", encoding="utf-8") as fp:
                fp.write(new_text)
        print(f"\nApplied {len(changes)} updates.")
    else:
        print("\nDry run complete. Add --apply to write changes.")

if __name__ == "__main__":
    main()
