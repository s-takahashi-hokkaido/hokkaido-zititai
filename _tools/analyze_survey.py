#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze survey.json and categorize results."""
import json, os, re
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "_tools", "survey.json"), encoding="utf-8") as fp:
    data = json.load(fp)

def pattern_key(url):
    if "harp.lg.jp" in url: return "A harp.lg.jp"
    if "logoform.jp" in url: return "B logoform.jp"
    if "cgi-bin/inquiry.php" in url: return "C cgi-bin/inquiry.php"
    if "cgi-bin/contacts" in url: return "D cgi-bin/contacts"
    if "form/detail.php" in url: return "E form/detail.php?sec_sec1="
    if "detail.php?content=" in url or "/content/?content=" in url: return "F content="
    if re.search(r"/inquiry/\d+(_sp)?\.html", url): return "G /inquiry/N.html"
    if re.search(r"/mail/\d+\.html", url): return "H /mail/N.html"
    if re.search(r"/inquiry/?$", url): return "I /inquiry/"
    if "/toiawase" in url: return "J /toiawase"
    if "/contacts/inquiry" in url: return "I /inquiry/"
    if "/contact/" in url or url.endswith("/contact") or url.endswith("/contact.html"): return "L /contact"
    if "/contacts" in url: return "K /contacts"
    if "/form/" in url or url.endswith("/form"): return "M /form"
    if "sec_form" in url: return "O sec_form"
    if "mailform" in url: return "P /mailform"
    if "inquiry.php" in url: return "Q inquiry.php"
    return "Z other"

# Categorize
by_pattern = defaultdict(list)
for r in data:
    by_pattern[pattern_key(r["url"])].append(r)

print("="*70)
print("SURVEY RESULT SUMMARY (124 URLs)")
print("="*70)
for pkey in sorted(by_pattern.keys()):
    items = by_pattern[pkey]
    ok = sum(1 for r in items if r.get("form_count",0) > 0)
    zero = sum(1 for r in items if r.get("form_count",0) == 0)
    captcha = sum(1 for r in items if r.get("captcha"))
    print(f"\n[{pkey}] {len(items)}件 | 静的OK={ok} JS/Cookie要={zero} CAPTCHA={captcha}")
    # Show field signature counts
    sig_counts = Counter()
    for r in items:
        for f in (r.get("forms") or []):
            names = tuple(sorted(fl["name"] for fl in f["fields"] if fl["name"] and fl["type"] != "hidden"))
            if names:
                sig_counts[names] += 1
    if sig_counts:
        print("  共通フィールドシグネチャ:")
        for sig, cnt in sig_counts.most_common(3):
            short = list(sig)[:8]
            print(f"    x{cnt}: {short}{'...' if len(sig)>8 else ''}")

# Zero-form cases
print("\n" + "="*70)
print(f"ZERO-FORM CASES (need Playwright/Cookie handling)")
print("="*70)
zeros = [r for r in data if r.get("form_count",0) == 0 and "error" not in r]
by_pz = defaultdict(list)
for r in zeros:
    by_pz[pattern_key(r["url"])].append(r)
for pkey in sorted(by_pz.keys()):
    print(f"\n[{pkey}] {len(by_pz[pkey])}件:")
    for r in by_pz[pkey]:
        print(f"  {r['name']:12} {r['url']}")

# CAPTCHA cases
print("\n" + "="*70)
print("CAPTCHA DETECTED")
print("="*70)
for r in data:
    if r.get("captcha"):
        print(f"  {r['name']:12} {r['captcha']} | {r['url']}")

# Detailed check: URLs where scraper found >1 form (ambiguity)
print("\n" + "="*70)
print("AMBIGUOUS (>1 non-search form)")
print("="*70)
for r in data:
    if r.get("form_count", 0) > 1:
        print(f"  {r['name']}: {r['form_count']} forms")
        for f in r["forms"]:
            names = [fl["name"] for fl in f["fields"] if fl["name"] and fl["type"] != "hidden"]
            print(f"    action={f['action'][:60]} fields({len(names)})={names[:6]}")
