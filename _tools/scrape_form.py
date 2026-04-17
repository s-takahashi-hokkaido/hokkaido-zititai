#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch a form URL and dump its structure:
- All <form> tags and their action/method
- All inputs (input/select/textarea) with name, id, type, required, placeholder
- CAPTCHA detection (reCAPTCHA, hCaptcha, image-based)
- Submit button identification
"""
import sys, re, json, ssl
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

CAPTCHA_PATTERNS = [
    ("reCAPTCHA v2/v3", re.compile(r"google\.com/recaptcha|grecaptcha|g-recaptcha|recaptcha/api\.js", re.I)),
    ("hCaptcha", re.compile(r"hcaptcha", re.I)),
    ("Cloudflare Turnstile", re.compile(r"turnstile|cf-turnstile", re.I)),
    ("Image CAPTCHA", re.compile(r"captcha_image|captcha\.png|captcha\.jpg|認証コード|画像認証", re.I)),
]

def fetch(url: str, timeout: int = 20):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, verify=True, allow_redirects=True)
    except requests.exceptions.SSLError:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, verify=False, allow_redirects=True)
    except Exception as e:
        return None, f"FETCH_ERROR: {type(e).__name__}: {e}"

    r.encoding = r.apparent_encoding or r.encoding or "utf-8"
    return r, None

def detect_captcha(html: str):
    found = []
    for name, pat in CAPTCHA_PATTERNS:
        if pat.search(html):
            found.append(name)
    return found

def dump_form(url: str):
    r, err = fetch(url)
    if err:
        return {"url": url, "error": err}
    html = r.text
    soup = BeautifulSoup(html, "lxml")

    captcha = detect_captcha(html)
    forms = []
    for idx, form in enumerate(soup.find_all("form")):
        action = form.get("action", "").strip()
        method = (form.get("method", "") or "GET").upper()
        fields = []
        for el in form.find_all(["input", "select", "textarea"]):
            tag = el.name
            name = el.get("name", "").strip()
            id_ = el.get("id", "").strip()
            typ = el.get("type", "").strip() if tag == "input" else tag
            required = (el.has_attr("required") or el.get("aria-required") == "true")
            placeholder = el.get("placeholder", "").strip()
            # skip hidden-only tokens we don't need to care about visibility-wise
            skip = (typ == "hidden" and name.lower() in {"_token","csrf_token","csrfmiddlewaretoken"})
            options = []
            if tag == "select":
                for opt in el.find_all("option"):
                    v = opt.get("value", "")
                    t = opt.get_text(strip=True)
                    if v or t:
                        options.append({"value": v, "text": t})
            fields.append({
                "tag": tag, "type": typ, "name": name, "id": id_,
                "required": required, "placeholder": placeholder,
                "hidden_token": skip,
                "options": options,
            })
        # detect submit button
        submits = form.find_all(["button", "input"], type=lambda t: t in ("submit", None))
        submit_info = []
        for s in submits:
            if s.name == "button":
                st = s.get("type", "submit")
                if st == "submit":
                    submit_info.append({"tag": "button", "name": s.get("name",""), "id": s.get("id",""), "text": s.get_text(strip=True)[:30]})
            elif s.name == "input" and s.get("type") == "submit":
                submit_info.append({"tag": "input[submit]", "name": s.get("name",""), "id": s.get("id",""), "value": s.get("value","")[:30]})
        forms.append({
            "index": idx,
            "action": action,
            "method": method,
            "fields": fields,
            "submits": submit_info,
        })

    return {
        "url": url,
        "status": r.status_code,
        "final_url": r.url,
        "encoding": r.encoding,
        "captcha": captcha,
        "form_count": len(forms),
        "forms": forms,
    }

if __name__ == "__main__":
    urls = sys.argv[1:]
    if not urls:
        print("usage: scrape_form.py <url> [<url> ...]")
        sys.exit(1)
    for url in urls:
        result = dump_form(url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("---")
