#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run extract_labels.analyze() on all 124 form URLs, save to labels.json."""
import os, re, sys, json, time
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_tools"))
from extract_labels import analyze

HOKKAIDO = os.path.join(ROOT, "北海道")
OUT = os.path.join(ROOT, "_tools", "labels.json")

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
    print(f"Collected {len(items)} URLs", flush=True)
    results = []
    for i, it in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {it['name']}", flush=True)
        r = analyze(it["url"])
        r.update({"path": it["path"], "name": it["name"], "region": it["region"]})
        results.append(r)
        time.sleep(0.3)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)
    print(f"Saved to {OUT}")

if __name__ == "__main__":
    main()
