#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwrightで form URL を開き、入力要素を一覧化する調査ツール。

MD の フォームフィールド テーブルが空（= Playwright調査が必要）な自治体を対象に、
各ページを1件ずつ開いて input/textarea/select を列挙し、
MD にコピペできる Markdown テーブル形式で `_tools/discover/{自治体名}.md` に出力する。

Examples:
  # 空フィールドの form 自治体を全部調査（18件程度）
  python _tools/discover_fields.py

  # 1件だけ試す
  python _tools/discover_fields.py --only 網走市 --show-browser

  # 既に出力済みの自治体をスキップして再開
  python _tools/discover_fields.py --resume
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from md_parser import load_all  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "discover"
NAV_TIMEOUT_MS = 30_000

# ラベル/placeholder/nameテキストから標準名への推測ルール
# ※順序重要（長い語を先に）
_NAME_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"メール.*確認|確認.*メール|メール.*再入力"), "メール確認"),
    (re.compile(r"メール|e[-_ ]?mail", re.I), "メールアドレス"),
    (re.compile(r"フリガナ|ふりがな|カナ|かな"), "フリガナ"),
    (re.compile(r"氏名|お名前|名前|ご芳名"), "名前"),
    (re.compile(r"郵便"), "郵便番号"),
    (re.compile(r"都道府県"), "都道府県"),
    (re.compile(r"住所|番地|町名"), "住所"),
    (re.compile(r"電話|tel", re.I), "電話番号"),
    (re.compile(r"年齢"), "年齢"),
    (re.compile(r"性別"), "性別"),
    (re.compile(r"職業|ご職業"), "職業"),
    (re.compile(r"件名|題名|タイトル|subject", re.I), "件名"),
    (re.compile(r"本文|内容|ご意見|ご要望|お問い合わ?せ内容|メッセージ|message|お問合せ", re.I), "本文"),
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="form フィールド調査ツール")
    ap.add_argument("--only", default="",
                    help="自治体名カンマ区切り（例: --only 網走市,江別市）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true",
                    help="既に _tools/discover/{自治体名}.md が存在する自治体はスキップ")
    ap.add_argument("--show-browser", action="store_true",
                    help="ブラウザを表示して実行（デバッグ用）")
    return ap.parse_args()


def pick_targets(args) -> list:
    """fields が空の form 自治体を対象に返す。"""
    recs = load_all()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    out = []
    for r in recs:
        if r.method != "form":
            continue
        if r.is_captcha_blocked:
            continue
        if r.fields:
            continue
        if not r.form_url:
            continue
        if only and r.name not in only:
            continue
        if args.resume and (OUT_DIR / f"{r.name}.md").exists():
            continue
        out.append(r)
    if args.limit:
        out = out[: args.limit]
    return out


def guess_canonical(text: str) -> str | None:
    if not text:
        return None
    for pat, canon in _NAME_RULES:
        if pat.search(text):
            return canon
    return None


def _selector_for(el: dict) -> str:
    """id / name / 最後の手段で :nth-of-type を使った CSS セレクタを返す。"""
    if el.get("id"):
        return f"#{el['id']}"
    if el.get("name"):
        return f'[name="{el["name"]}"]'
    # フォールバック（あまり推奨しない）
    return el.get("tag", "input")


def _normalize_type(tag: str, input_type: str | None) -> str:
    t = (input_type or "").lower()
    if tag == "textarea":
        return "textarea"
    if tag == "select":
        return "select"
    if t == "radio":
        return "radio"
    if t == "checkbox":
        return "checkbox"
    if t in ("submit", "button", "reset", "image"):
        return "button"
    if t == "hidden":
        return "hidden"
    # text / email / tel / number / url / search / etc.
    return "text"


JS_COLLECT = """
() => {
  const result = [];
  const isSearchForm = (f) => {
    const hay = ((f.getAttribute('action')||'') + ' ' +
                 (f.getAttribute('id')||'') + ' ' +
                 (f.getAttribute('class')||'') + ' ' +
                 (f.getAttribute('name')||'')).toLowerCase();
    if (/search|cse|google|query/.test(hay)) return true;
    const fields = f.querySelectorAll('input:not([type=hidden]),textarea,select');
    if (fields.length <= 2) {
      const names = Array.from(fields).map(e => (e.name||'').toLowerCase()).join(',');
      if (/^q$|,q$|^q,/.test(names)) return true;
    }
    return false;
  };
  // 同一オリジンの iframe 内も走査
  const docs = [document];
  for (const iframe of document.querySelectorAll('iframe')) {
    try {
      const d = iframe.contentDocument;
      if (d) docs.push(d);
    } catch (e) { /* cross-origin skip */ }
  }
  const allForms = [];
  for (const d of docs) {
    allForms.push(...Array.from(d.querySelectorAll('form')).filter(f => !isSearchForm(f)));
  }
  // ページ内で最もフィールドが多い問合せ系formを採用（無ければdocument全体）
  let scope = document;
  if (allForms.length > 0) {
    scope = allForms.sort((a, b) =>
      b.querySelectorAll('input,textarea,select').length -
      a.querySelectorAll('input,textarea,select').length)[0];
  }
  const labelFor = (id) => {
    if (!id) return '';
    const lbl = document.querySelector(`label[for="${CSS.escape(id)}"]`);
    return lbl ? lbl.innerText.trim() : '';
  };
  const closestLabel = (el) => {
    const lbl = el.closest('label');
    return lbl ? lbl.innerText.trim() : '';
  };
  const parentLegend = (el) => {
    const fs = el.closest('fieldset');
    if (!fs) return '';
    const lg = fs.querySelector('legend');
    return lg ? lg.innerText.trim() : '';
  };
  const nearbyText = (el) => {
    // 直前の th / dt / preceding sibling text を雑に拾う
    const row = el.closest('tr,dl,dt,li,div');
    if (!row) return '';
    const th = row.querySelector('th,dt');
    if (th && !th.contains(el)) return th.innerText.trim();
    return '';
  };
  const collapseWs = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const truncate = (s, n) => (s && s.length > n) ? (s.slice(0, n) + '…') : s;
  const rowContext = (el) => {
    // 同じ tr / dl / fieldset / li 内のテキスト全体
    const row = el.closest('tr,dl,fieldset,li');
    if (!row) return '';
    // 入力値が混ざらないよう innerText を使う（inputのvalueは含まない）
    return truncate(collapseWs(row.innerText), 200);
  };
  const prevSiblingText = (el) => {
    let cur = el.previousElementSibling;
    let steps = 0;
    while (cur && steps < 3) {
      const t = collapseWs(cur.innerText);
      if (t) return truncate(t, 120);
      cur = cur.previousElementSibling;
      steps++;
    }
    // 親の previousSibling も見る
    const parent = el.parentElement;
    if (parent) {
      cur = parent.previousElementSibling;
      steps = 0;
      while (cur && steps < 3) {
        const t = collapseWs(cur.innerText);
        if (t) return truncate(t, 120);
        cur = cur.previousElementSibling;
        steps++;
      }
    }
    return '';
  };
  const ancestorHeading = (el) => {
    // 祖先を辿って最初の h1-h6 / [class*=title] / [class*=label] のテキスト
    let cur = el.parentElement;
    let steps = 0;
    while (cur && steps < 6) {
      const h = cur.querySelector('h1,h2,h3,h4,h5,h6,[class*="title"],[class*="label"],[class*="Label"]');
      if (h && !h.contains(el)) {
        const t = collapseWs(h.innerText);
        if (t) return truncate(t, 120);
      }
      cur = cur.parentElement;
      steps++;
    }
    return '';
  };
  const items = Array.from(scope.querySelectorAll('input,textarea,select'));
  for (const el of items) {
    result.push({
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      name: el.name || '',
      id: el.id || '',
      placeholder: el.placeholder || '',
      ariaLabel: el.getAttribute('aria-label') || '',
      required: el.required || el.getAttribute('aria-required') === 'true',
      label: labelFor(el.id) || closestLabel(el) || '',
      legend: parentLegend(el),
      nearby: nearbyText(el),
      rowContext: rowContext(el),
      prevSibling: prevSiblingText(el),
      ancestorHeading: ancestorHeading(el),
    });
  }
  return result;
}
"""


def render_md(name: str, url: str, elements: list[dict],
              final_url: str | None = None, visited: list[str] | None = None) -> str:
    # button/hidden を除外した入力要素のみテーブル化
    input_rows = []
    button_rows = []
    for el in elements:
        t = _normalize_type(el["tag"], el["type"])
        if t == "hidden":
            continue
        sel = _selector_for(el)
        label_source = " / ".join(filter(None, [
            el.get("label"), el.get("legend"), el.get("nearby"),
            el.get("prevSibling"), el.get("ancestorHeading"),
            el.get("ariaLabel"), el.get("placeholder"), el.get("rowContext"),
            el.get("name"),
        ]))
        canon = guess_canonical(label_source) or "?"
        req = "○" if el.get("required") else ""
        if t == "button":
            button_rows.append((canon, sel, t, req, label_source))
        else:
            input_rows.append((canon, sel, t, req, label_source))

    lines = [
        f"# {name} フォーム調査結果",
        "",
        f"- 指定URL: {url}",
    ]
    if final_url and final_url != url:
        lines.append(f"- **実フォームURL**: {final_url}")
    if visited and len(visited) > 1:
        lines.append(f"- 遷移経路: {' → '.join(visited)}")
    lines += [
        f"- 検出要素数: input/textarea/select = {len(input_rows)}, button = {len(button_rows)}",
        "",
        "## 推奨フィールドテーブル（MDへコピペ）",
        "",
        "> 「フィールド名」列は自動推定。`?` は要手動マッピング。",
        "",
        "| フィールド名 | セレクタ | 入力タイプ | 必須 | 固定値 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for canon, sel, t, req, _src in input_rows:
        lines.append(f"| {canon} | {sel} | {t} | {req} |  |")
    lines.append("")
    lines.append("## 送信ボタン候補")
    lines.append("")
    if button_rows:
        lines.append("| セレクタ | 種別 | ラベル/name |")
        lines.append("| --- | --- | --- |")
        for _c, sel, t, _r, src in button_rows:
            lines.append(f"| {sel} | {t} | {src} |")
    else:
        lines.append("（検出なし — ページに submit ボタンが見えていない可能性）")
    lines.append("")
    lines.append("## 生データ")
    lines.append("")
    for i, el in enumerate(elements, 1):
        lines.append(
            f"{i}. **tag**={el['tag']} **type**={el['type']!r} "
            f"**name**={el['name']!r} **id**={el['id']!r} "
            f"**required**={el['required']}"
        )
        for key, label in [
            ("label", "label"),
            ("legend", "legend"),
            ("nearby", "nearby(th/dt)"),
            ("prevSibling", "prevSibling"),
            ("ancestorHeading", "ancestorHeading"),
            ("ariaLabel", "aria-label"),
            ("placeholder", "placeholder"),
            ("rowContext", "rowContext"),
        ]:
            v = el.get(key) or ""
            if v:
                lines.append(f"    - {label}: {v}")
    lines.append("")
    return "\n".join(lines)


_SEARCH_NAMES = {"q", "tmp_query", "open_page_id", "sa", "open_page_id_submit"}
_NOISE_ID_PREFIXES = ("goog-gt", "google_translate")


def _is_low_quality(elements: list[dict]) -> bool:
    """検索系/翻訳ウィジェット/hidden を除いて意味のある入力要素が少なければ True。"""
    meaningful = 0
    for el in elements:
        t = _normalize_type(el["tag"], el["type"])
        if t in ("hidden", "button"):
            continue
        name = (el.get("name") or "").lower()
        eid = (el.get("id") or "").lower()
        if name in _SEARCH_NAMES or name.startswith(("google_", "filetype")):
            continue
        if any(eid.startswith(p) for p in _NOISE_ID_PREFIXES):
            continue
        meaningful += 1
    return meaningful < 3


_COOKIE_ERROR_MARKERS = (
    "ご利用頂けません",
    "ご利用いただけません",
    "Cookie（クッキー）",
    "Cookie(クッキー)",
)


def _has_blocking_message(page) -> bool:
    try:
        body = page.inner_text("body", timeout=3_000)
    except Exception:
        return False
    return any(m in body for m in _COOKIE_ERROR_MARKERS)


def _find_contact_link(page, current_url: str) -> str | None:
    """ページ内の「お問い合わせ」リンクのうち、current_url と異なるものを1つ返す。"""
    try:
        hrefs = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a'))
              .filter(a => /お問い?合わせ|問合せ|ご意見/.test(a.innerText || ''))
              .map(a => a.href)
              .filter(h => h && !h.startsWith('javascript:'))
            """
        )
    except Exception:
        return None
    for h in hrefs:
        # フラグメント除去で同一性比較
        if h.split("#")[0] != current_url.split("#")[0]:
            return h
    return None


def investigate(page, url: str, shot_path: Path) -> tuple[list[dict], str, list[str]]:
    """対象URLを開いて入力要素を走査。低品質ならお問い合わせリンクを辿って再試行。

    先にオリジンのトップページを踏んでセッションCookieを確立させる。
    （一部自治体サイトは Cookie 無しだとフォーム非表示になる）
    """
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        try:
            page.goto(f"{parsed.scheme}://{parsed.netloc}/",
                      timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        except Exception:
            pass
    # `&check` 付きURLはサーバー側でCookie検証するタイプ。先に無し版を踏んで
    # Cookie をセットしてもらう（例: 厚沢部町）。
    if "&check" in url or "?check" in url:
        no_check = url.replace("&check", "").replace("?check", "")
        try:
            page.goto(no_check, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        except Exception:
            pass
    visited: list[str] = []
    current = url
    elements: list[dict] = []
    for attempt in range(3):
        if current in visited:
            break
        visited.append(current)
        page.goto(current, timeout=NAV_TIMEOUT_MS)
        page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        elements = page.evaluate(JS_COLLECT)
        blocked = _has_blocking_message(page)
        if not blocked and not _is_low_quality(elements):
            break
        next_url = _find_contact_link(page, current)
        if not next_url or next_url in visited:
            break
        current = next_url
    try:
        page.screenshot(path=str(shot_path), full_page=True)
    except Exception:
        pass
    return elements, current, visited


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = pick_targets(args)
    print(f"[discover] targets={len(targets)}")
    if not targets:
        return 0

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show_browser)
        context = browser.new_context()
        page = context.new_page()
        try:
            for i, m in enumerate(targets, 1):
                print(f"[{i}/{len(targets)}] {m.region}/{m.name} ... ", end="", flush=True)
                shot_path = OUT_DIR / f"{m.name}.png"
                try:
                    elements, final_url, visited = investigate(page, m.form_url, shot_path)
                except Exception as e:  # noqa: BLE001
                    print(f"ERROR {type(e).__name__}: {e}")
                    continue
                md = render_md(m.name, m.form_url, elements, final_url, visited)
                out_path = OUT_DIR / f"{m.name}.md"
                out_path.write_text(md, encoding="utf-8")
                tag = f" (→ {final_url})" if final_url != m.form_url else ""
                print(f"{len(elements)} elements -> {out_path.name}{tag}")
        finally:
            context.close()
            browser.close()
    print("[discover] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
