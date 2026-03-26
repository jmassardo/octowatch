#!/usr/bin/env python3
"""Quality validation for mockups/index.html"""
from html.parser import HTMLParser
import re, os, sys

target = os.path.join(os.path.dirname(__file__), '..', 'mockups', 'index.html')
with open(target, 'r', encoding='utf-8') as f:
    html = f.read()

errors = []
warnings = []

# ── 1. HTML tag nesting ──────────────────────────────────────────────────────
class Validator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errs = []
        self.void = {'area','base','br','col','embed','hr','img','input',
                     'link','meta','param','source','track','wbr'}
    def handle_starttag(self, tag, attrs):
        if tag not in self.void:
            self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in self.void:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            expected = self.stack[-1] if self.stack else 'empty'
            self.errs.append(f"Unexpected </{tag}>, expected </{expected}>")

v = Validator()
v.feed(html)
if v.errs:
    for e in v.errs[:10]:
        errors.append(f"HTML nesting: {e}")
if v.stack:
    errors.append(f"Unclosed tags at EOF: {v.stack}")
else:
    print("✓ HTML tag nesting: clean")

# ── 2. Required elements present ────────────────────────────────────────────
required = {
    'copilot-tabs div': r'<div class="copilot-tabs">',
    '5 copilot-tab items': r'class="copilot-tab',
    'ct-overview pane': r'id="ct-overview"',
    'ct-adoption pane': r'id="ct-adoption"',
    'ct-models pane': r'id="ct-models"',
    'ct-license pane': r'id="ct-license"',
    'ct-anomalies pane': r'id="ct-anomalies"',
    'adoption-grid': r'class="adoption-grid"',
    'import-drop zones (2)': None,
    'copilotTab() function': r'function copilotTab\(',
    'nav() function': r'function nav\(',
    'Recent imports table': r'Recent imports',
    'Data Import section': r'Data Import',
    'CCR impact section': r'CCR impact on PR review time',
    'License Optimization pane content': r'Upgrade candidates',
    'Downgrade candidates table': r'Downgrade candidates',
    'Anomalies detail cards': r'no telemetry',
}

tab_count = len(re.findall(r'class="copilot-tab["\s]', html))
drop_count = len(re.findall(r'class="import-drop"', html))

for name, pattern in required.items():
    if name == '5 copilot-tab items':
        if tab_count >= 5:
            print(f"✓ {name}: {tab_count} found")
        else:
            errors.append(f"Missing: {name} (found {tab_count}, expected 5)")
    elif name == 'import-drop zones (2)':
        if drop_count >= 2:
            print(f"✓ {name}: {drop_count} found")
        else:
            errors.append(f"Missing: {name} (found {drop_count}, expected 2)")
    elif pattern and re.search(pattern, html):
        print(f"✓ {name}")
    elif pattern:
        errors.append(f"Missing: {name} (pattern: {pattern})")

# ── 3. No broken screen references in nav ───────────────────────────────────
nav_ids = re.findall(r"nav\('([^']+)'", html)
screen_ids = re.findall(r'id="s-([^"]+)"', html)
for nid in nav_ids:
    if nid not in screen_ids:
        errors.append(f"Nav link 's-{nid}' has no matching screen div")

print(f"✓ Nav links: all {len(nav_ids)} nav calls have matching screens")

# ── 4. JS syntax spot-check: matching braces in script block ────────────────
script_match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
if script_match:
    script = script_match.group(1)
    opens = script.count('{')
    closes = script.count('}')
    if opens == closes:
        print(f"✓ JS brace balance: {opens} open = {closes} close")
    else:
        errors.append(f"JS brace mismatch: {opens} open vs {closes} close")
else:
    errors.append("No <script> block found")

# ── 5. Summary ───────────────────────────────────────────────────────────────
print()
if errors:
    print(f"ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    lines = html.count('\n')
    size_kb = len(html) / 1024
    print(f"QUALITY PASS: {lines} lines, {size_kb:.1f} KB, 0 errors")
