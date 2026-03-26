#!/usr/bin/env python3
"""Add Import Data section to Integrations screen and copilotTab() JS function."""
import sys, os

target = os.path.join(os.path.dirname(__file__), '..', 'mockups', 'index.html')
with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. Add Import Data section to Integrations ──────────────────────────────
OLD_INTEG_END = '''      </div>
    </div>
  </div>

</div><!-- /main -->'''

NEW_INTEG_END = '''      </div>

      <!-- Data Import -->
      <div class="section-title" style="margin-top:24px">Data Import</div>
      <div style="font-size:12px;color:var(--fg-muted);margin-bottom:16px">
        Import exported data files to analyze without live API access &mdash; great for evaluating OctoWatch before full deployment or filling historical gaps.
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px">
        <!-- Audit Log Import -->
        <div class="card">
          <div class="card-header" style="margin-bottom:12px">
            <span style="display:flex;align-items:center;gap:8px">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="var(--fg-muted)"><path d="M1.75 2.5a.25.25 0 000 .5h12.5a.25.25 0 000-.5H1.75zM1.5 6.75A.75.75 0 012.25 6h11.5a.75.75 0 010 1.5H2.25A.75.75 0 011.5 6.75zm0 4.5a.75.75 0 01.75-.75h5.5a.75.75 0 010 1.5h-5.5a.75.75 0 01-.75-.75z"/></svg>
              Audit Log Import
            </span>
          </div>
          <div class="import-drop" onclick="this.nextElementSibling.click()">
            <svg width="24" height="24" viewBox="0 0 16 16" fill="var(--fg-subtle)" style="margin-bottom:8px"><path d="M7.47 1.47a.75.75 0 011.06 0l3.5 3.5a.75.75 0 01-1.06 1.06L8.75 3.81V9.5a.75.75 0 01-1.5 0V3.81L5.03 6.03a.75.75 0 01-1.06-1.06l3.5-3.5zm-3.97 9.5a.75.75 0 010-1.5h1.99a.75.75 0 010 1.5H3.5zm8.01 0a.75.75 0 010-1.5H13.5a.75.75 0 010 1.5h-1.99zM1.75 13.5a.25.25 0 00-.25.25V14a.25.25 0 00.25.25h12.5A.25.25 0 0014.5 14v-.25a.25.25 0 00-.25-.25H1.75z"/></svg>
            <div style="font-size:13px;color:var(--fg-muted)">Drop file here or <span style="color:var(--accent)">browse</span></div>
            <div style="font-size:11px;color:var(--fg-subtle);margin-top:4px">Accepts .csv or .json &middot; max 500 MB</div>
          </div>
          <input type="file" accept=".csv,.json" style="display:none">
          <div style="margin-top:10px;font-size:12px;color:var(--fg-muted)">
            Export from GitHub Enterprise: <code style="font-size:11px;background:var(--canvas-inset);padding:1px 4px;border-radius:3px">Settings &rarr; Audit log &rarr; Export CSV</code>
          </div>
        </div>
        <!-- Copilot Metrics Import -->
        <div class="card">
          <div class="card-header" style="margin-bottom:12px">
            <span style="display:flex;align-items:center;gap:8px">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="var(--fg-muted)"><path d="M0 2.75A2.75 2.75 0 012.75 0h10.5A2.75 2.75 0 0116 2.75v10.5A2.75 2.75 0 0113.25 16H2.75A2.75 2.75 0 010 13.25zM2.75 1.5c-.69 0-1.25.56-1.25 1.25v10.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25V2.75c0-.69-.56-1.25-1.25-1.25zM8 4a.75.75 0 01.75.75v3.69l1.47-1.47a.75.75 0 011.06 1.06l-2.75 2.75a.75.75 0 01-1.06 0L4.72 8.03a.75.75 0 011.06-1.06L7.25 8.46V4.75A.75.75 0 018 4z"/></svg>
              Copilot Metrics Import
            </span>
          </div>
          <div class="import-drop" onclick="this.nextElementSibling.click()">
            <svg width="24" height="24" viewBox="0 0 16 16" fill="var(--fg-subtle)" style="margin-bottom:8px"><path d="M7.47 1.47a.75.75 0 011.06 0l3.5 3.5a.75.75 0 01-1.06 1.06L8.75 3.81V9.5a.75.75 0 01-1.5 0V3.81L5.03 6.03a.75.75 0 01-1.06-1.06l3.5-3.5zm-3.97 9.5a.75.75 0 010-1.5h1.99a.75.75 0 010 1.5H3.5zm8.01 0a.75.75 0 010-1.5H13.5a.75.75 0 010 1.5h-1.99zM1.75 13.5a.25.25 0 00-.25.25V14a.25.25 0 00.25.25h12.5A.25.25 0 0014.5 14v-.25a.25.25 0 00-.25-.25H1.75z"/></svg>
            <div style="font-size:13px;color:var(--fg-muted)">Drop file here or <span style="color:var(--accent)">browse</span></div>
            <div style="font-size:11px;color:var(--fg-subtle);margin-top:4px">Accepts .json &middot; GitHub Copilot Metrics API format</div>
          </div>
          <input type="file" accept=".json" style="display:none">
          <div style="margin-top:10px;font-size:12px;color:var(--fg-muted)">
            Fetch via: <code style="font-size:11px;background:var(--canvas-inset);padding:1px 4px;border-radius:3px">GET /orgs/{org}/copilot/metrics</code>
          </div>
        </div>
      </div>

      <!-- Recent imports -->
      <div class="section-title" style="margin-bottom:10px">Recent imports</div>
      <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden">
        <table>
          <thead><tr><th>File</th><th>Type</th><th>Size</th><th>Imported at</th><th>Records</th><th>Status</th></tr></thead>
          <tbody>
            <tr><td style="color:var(--fg-muted);font-variant-numeric:tabular-nums">audit-log-jan-2026.json</td><td><span class="label label-muted">audit_log</span></td><td style="color:var(--fg-muted)">48.2 MB</td><td style="color:var(--fg-muted)">Mar 20, 2026 09:14</td><td style="font-variant-numeric:tabular-nums">124,832</td><td><span class="label label-success">complete</span></td></tr>
            <tr><td style="color:var(--fg-muted)">copilot-metrics-q1.json</td><td><span class="label label-muted">copilot</span></td><td style="color:var(--fg-muted)">2.1 MB</td><td style="color:var(--fg-muted)">Mar 18, 2026 14:02</td><td style="font-variant-numeric:tabular-nums">8,640</td><td><span class="label label-success">complete</span></td></tr>
            <tr><td style="color:var(--fg-muted)">audit-log-dec-2025.csv</td><td><span class="label label-muted">audit_log</span></td><td style="color:var(--fg-muted)">31.7 MB</td><td style="color:var(--fg-muted)">Jan 5, 2026 11:47</td><td style="font-variant-numeric:tabular-nums">89,441</td><td><span class="label label-success">complete</span></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div><!-- /main -->'''

if OLD_INTEG_END not in content:
    print("ERROR: integrations end marker not found", file=sys.stderr)
    sys.exit(1)

content = content.replace(OLD_INTEG_END, NEW_INTEG_END, 1)

# ── 2. Add copilotTab() JS function before closing </script> ────────────────
OLD_JS = '''function nav(id, el) {'''

NEW_JS = '''function copilotTab(id, el) {
  document.querySelectorAll('.copilot-pane').forEach(p => { p.style.display=''; p.classList.remove('active'); });
  const pane = document.getElementById('ct-' + id);
  if (pane) pane.classList.add('active');
  document.querySelectorAll('.copilot-tab').forEach(t => t.classList.remove('active'));
  if (el) el.classList.add('active');
}

function nav(id, el) {'''

if OLD_JS not in content:
    print("ERROR: nav() function marker not found", file=sys.stderr)
    sys.exit(1)

content = content.replace(OLD_JS, NEW_JS, 1)

with open(target, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"SUCCESS: file updated, total {len(content)} chars")

# Quick verification
assert 'id="ct-overview"' in content
assert 'id="ct-anomalies"' in content
assert 'copilotTab' in content
assert 'import-drop' in content
assert 'Recent imports' in content
print("All assertions passed.")
