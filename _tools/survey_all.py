#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Survey all 124 form URLs and save findings to JSON.
Uses requests session (handles cookies) + BeautifulSoup.
"""
import os, re, sys, json, time
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOKKAIDO = os.path.join(ROOT, "北海道")
OUT = os.path.join(ROOT, "_tools", "survey.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

CAPTCHA_PATTERNS = [
    ("reCAPTCHA", re.compile(r"google\.com/recaptcha|grecaptcha|g-recaptcha|recaptcha/api\.js", re.I)),
    ("hCaptcha", re.compile(r"hcaptcha", re.I)),
    ("Turnstile", re.compile(r"turnstile|cf-turnstile", re.I)),
    ("Image CAPTCHA", re.compile(r"captcha_image|captcha\.png|captcha\.jpg|認証コード|画像認証", re.I)),
]

# URLs known to require JavaScript (no form tag renders server-side)
JS_REQUIRED_HINTS = ["logoform.jp"]

def detect_captcha(html):
    return [name for name, pat in CAPTCHA_PATTERNS if pat.search(html)]

def list_inputs(form):
    fields = []
    for el in form.find_all(["input", "select", "textarea"]):
        tag = el.name
        name = (el.get("name") or "").strip()
        id_ = (el.get("id") or "").strip()
        typ = (el.get("type") or "").strip() if tag == "input" else tag
        required = (el.has_attr("required") or el.get("aria-required") == "true")
        placeholder = (el.get("placeholder") or "").strip()
        if typ == "hidden" and not name:
            continue
        fields.append({
            "tag": tag, "type": typ, "name": name, "id": id_,
            "required": required, "placeholder": placeholder,
        })
    return fields

def analyze_url(session, url, is_retry=False):
    try:
        r = session.get(url, headers={"User-Agent": UA}, timeout=20, verify=True, allow_redirects=True)
    except requests.exceptions.SSLError:
        try:
            r = session.get(url, headers={"User-Agent": UA}, timeout=20, verify=False, allow_redirects=True)
        except Exception as e:
            return {"error": f"SSL+fallback: {type(e).__name__}: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    r.encoding = r.apparent_encoding or r.encoding or "utf-8"
    html = r.text
    soup = BeautifulSoup(html, "lxml")

    # Filter out site search forms (heuristic: action contains /search or fields are just cx/cof/ie/q/sa)
    all_forms = soup.find_all("form")
    result_forms = []
    for idx, form in enumerate(all_forms):
        action = (form.get("action") or "").strip()
        method = (form.get("method") or "GET").upper()
        fields = list_inputs(form)
        names = [f["name"] for f in fields if f["name"]]
        # skip Google custom search / site search
        is_search = ("/search" in action or action.endswith("/search/")
                     or set(names) <= {"cx","cof","ie","q","sa","s"} and len(names) <= 5)
        if is_search:
            continue
        result_forms.append({
            "index": idx,
            "action": action,
            "method": method,
            "fields": fields,
            "field_count_visible": sum(1 for f in fields if f["type"] not in ("hidden",)),
            "field_count_total": len(fields),
        })

    return {
        "status": r.status_code,
        "final_url": r.url,
        "encoding": r.encoding,
        "captcha": detect_captcha(html),
        "form_count": len(result_forms),
        "forms": result_forms,
        "html_length": len(html),
        "js_required_hint": any(h in url for h in JS_REQUIRED_HINTS),
    }

def collect_form_urls():
    items = []
    for root, _, files in os.walk(HOKKAIDO):
        for f in files:
            if not f.endswith(".md"): continue
            path = os.path.join(root, f)
            with open(path, encoding="utf-8") as fp:
                text = fp.read()
            m_method = re.search(r"\|\s*連絡手段\s*\|\s*(\S+)\s*\|", text)
            m_url = re.search(r"\|\s*フォームURL\s*\|\s*(\S+)\s*\|", text)
            if m_method and m_method.group(1) == "form" and m_url and m_url.group(1) not in ("-",""):
                items.append({
                    "path": os.path.relpath(path, ROOT).replace("\\","/"),
                    "name": os.path.splitext(f)[0],
                    "region": os.path.basename(os.path.dirname(path)),
                    "url": m_url.group(1),
                })
    return items

def main():
    items = collect_form_urls()
    print(f"Collected {len(items)} form URLs", flush=True)

    results = []
    session = requests.Session()
    for i, it in enumerate(items, 1):
        url = it["url"]
        print(f"[{i}/{len(items)}] {it['name']} {url[:80]}", flush=True)
        t0 = time.time()
        info = analyze_url(session, url)
        info["elapsed_ms"] = int((time.time()-t0)*1000)
        results.append({**it, **info})
        # Be polite to servers
        time.sleep(0.3)

    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUT}")

    # Quick stats
    err = sum(1 for r in results if "error" in r)
    zero = sum(1 for r in results if r.get("form_count") == 0 and "error" not in r)
    captcha = sum(1 for r in results if r.get("captcha"))
    print(f"Errors: {err}")
    print(f"Zero forms (JS/cookie required): {zero}")
    print(f"CAPTCHA detected: {captcha}")

if __name__ == "__main__":
    main()
