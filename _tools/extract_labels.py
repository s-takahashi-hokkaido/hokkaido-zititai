#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract form field labels with robust lookup.
Labels are sourced in priority order:
  1. <label for="id">
  2. Walk ancestors; for each <td>/<dd>, look for sibling <th>/<dt>
  3. <legend> in ancestor fieldset
  4. Wrapping <label>
  5. Fallback: closest preceding heading text
Required is detected via:
  - required attribute / aria-required
  - "必須"/"required"/"*"/"※" in label or parent row text
"""
import sys, re, json, os
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

REQUIRED_RE = re.compile(r"(必須|required|\*|※)", re.I)

def fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20, verify=True, allow_redirects=True)
    except requests.exceptions.SSLError:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20, verify=False, allow_redirects=True)
    r.encoding = r.apparent_encoding or r.encoding or "utf-8"
    return r

def find_label(soup, el):
    # 1. label[for=id]
    id_ = el.get("id", "")
    if id_:
        lab = soup.find("label", attrs={"for": id_})
        if lab:
            return lab.get_text(" ", strip=True), "label[for]"
    # 2. Walk ancestors to find a <td>/<dd> whose sibling is <th>/<dt>
    for anc in el.parents:
        if anc.name in ("td", "dd"):
            prev = anc.find_previous_sibling(["th","dt"])
            if prev:
                return prev.get_text(" ", strip=True), "th/dt"
        if anc.name == "fieldset":
            lg = anc.find("legend")
            if lg:
                return lg.get_text(" ", strip=True), "legend"
        if anc.name == "form":
            break
    # 3. wrapping label
    pl = el.find_parent("label")
    if pl:
        return pl.get_text(" ", strip=True), "wrap_label"
    # 4. previous <dt> or <th> in DOM order
    prev = el.find_previous(["dt","th","label","legend"])
    if prev:
        t = prev.get_text(" ", strip=True)
        if t and len(t) < 50:
            return t, "prev_heading"
    return "", "none"

def is_required(el, label, context_text):
    if el.has_attr("required") or el.get("aria-required") == "true":
        return True
    if REQUIRED_RE.search(label or ""):
        return True
    if REQUIRED_RE.search(context_text or ""):
        return True
    return False

def context_text(el):
    # Get text of parent tr/li/dl/div up to 2 levels
    for anc in el.parents:
        if anc.name in ("tr","li","dl"):
            return anc.get_text(" ", strip=True)
    p = el.find_parent("div")
    if p:
        return p.get_text(" ", strip=True)
    return ""

def pick_best_form(soup):
    best = None
    best_visible = -1
    for f in soup.find_all("form"):
        action = (f.get("action") or "").strip()
        if "/search" in action or action.endswith("/search/"):
            continue
        visible = [e for e in f.find_all(["input","select","textarea"]) if e.get("type") != "hidden"]
        if len(visible) > best_visible:
            best_visible = len(visible)
            best = f
    return best

def analyze(url):
    try:
        r = fetch(url)
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {e}"}
    soup = BeautifulSoup(r.text, "lxml")
    form = pick_best_form(soup)
    if not form:
        return {"url": url, "error": "no_form", "html_length": len(r.text)}
    result = {
        "url": url,
        "final_url": r.url,
        "action": (form.get("action") or "").strip(),
        "method": (form.get("method") or "GET").upper(),
        "fields": [],
    }
    seen_radio_groups = set()
    for el in form.find_all(["input","select","textarea","button"]):
        name = (el.get("name") or "").strip()
        id_ = (el.get("id") or "").strip()
        tag = el.name
        if tag == "button":
            typ = (el.get("type") or "submit").strip()
        else:
            typ = (el.get("type") or "").strip() if tag == "input" else tag
        if typ == "hidden":
            continue
        # for radio groups, we want the group's context label (from ancestor tr), not per-option
        label, src = find_label(soup, el)
        ctx = context_text(el)
        req = is_required(el, label, ctx)
        options = []
        if tag == "select":
            for opt in el.find_all("option"):
                t = opt.get_text(strip=True)
                if t:
                    options.append(t)
        entry = {
            "name": name, "id": id_, "type": typ,
            "label": label[:80], "label_src": src,
            "required": req,
            "options": options[:10],
        }
        # suppress duplicate radio rows
        if typ == "radio" and name in seen_radio_groups:
            entry["_dup_radio"] = True
        seen_radio_groups.add(name) if typ == "radio" else None
        result["fields"].append(entry)
    return result

if __name__ == "__main__":
    for u in sys.argv[1:]:
        print(json.dumps(analyze(u), ensure_ascii=False, indent=2))
        print("---")
