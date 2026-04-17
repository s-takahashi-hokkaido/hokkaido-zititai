#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Group form URLs by pattern for step 2 planning."""
import os, re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOKKAIDO = os.path.join(ROOT, "北海道")

urls = []
for root, dirs, files in os.walk(HOKKAIDO):
    for f in files:
        if f.endswith(".md"):
            path = os.path.join(root, f)
            with open(path, encoding="utf-8") as fp:
                text = fp.read()
            m_method = re.search(r"\|\s*連絡手段\s*\|\s*(\S+)\s*\|", text)
            m_url = re.search(r"\|\s*フォームURL\s*\|\s*(\S*)\s*\|", text)
            if m_method and m_method.group(1) == "form" and m_url:
                urls.append((m_url.group(1), path))

groups = defaultdict(list)
for url, path in urls:
    if "harp.lg.jp" in url:
        key = "A: harp.lg.jp (北海道共通電子申請)"
    elif "logoform.jp" in url:
        key = "B: logoform.jp (LoGoフォーム)"
    elif "cgi-bin/inquiry.php" in url:
        key = "C: cgi-bin/inquiry.php/N"
    elif "cgi-bin/contacts" in url:
        key = "D: cgi-bin/contacts/GXXX"
    elif "form/detail.php" in url:
        key = "E: form/detail.php?sec_sec1= (共通CMS)"
    elif "detail.php?content=" in url or "/content/?content=" in url:
        key = "F: detail.php?content="
    elif re.search(r"/inquiry/\d+(?:_sp)?\.html", url):
        key = "G: /inquiry/N.html"
    elif re.search(r"/mail/\d+\.html", url):
        key = "H: /mail/N.html"
    elif re.search(r"/inquiry/?$", url):
        key = "I: /inquiry/ (末尾)"
    elif "/toiawase" in url:
        key = "J: /toiawase"
    elif "/contacts" in url:
        key = "K: /contacts"
    elif "/contact/" in url or url.endswith("/contact") or url.endswith("/contact.html"):
        key = "L: /contact/ or /contact.html"
    elif "/form/" in url or url.endswith("/form"):
        key = "M: /form or /form/"
    elif "sec_form" in url:
        key = "O: sec_form/secN/"
    elif "mailform" in url:
        key = "P: /mailform/"
    elif "inquiry.php" in url:
        key = "Q: inquiry.php (独自)"
    else:
        key = "Z: other (個別対応)"
    groups[key].append((url, path))

total = sum(len(v) for v in groups.values())
print(f"TOTAL: {total}件\n")
for key in sorted(groups.keys()):
    items = groups[key]
    print(f"\n【{key}】 {len(items)}件")
    for url, path in items:
        name = os.path.splitext(os.path.basename(path))[0]
        region = os.path.basename(os.path.dirname(path))
        print(f"  {region}/{name:12} {url}")
