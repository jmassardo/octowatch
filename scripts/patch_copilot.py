#!/usr/bin/env python3
"""Replace the Copilot Insights screen in mockups/index.html with a 5-tab version."""
import sys, os

NEW_COPILOT = r"""  <!-- ===== COPILOT INSIGHTS ===== -->
  <div id="s-copilot" class="screen">
    <div class="screen-scroll">
      <div class="page-title">Copilot Insights</div>
      <div class="page-sub">GitHub Copilot adoption, seat utilization, model &amp; feature spread, and license optimization</div>

      <!-- Sub-navigation -->
      <div class="copilot-tabs">
        <div class="copilot-tab active" onclick="copilotTab('overview',this)">Overview</div>
        <div class="copilot-tab" onclick="copilotTab('adoption',this)">Adoption</div>
        <div class="copilot-tab" onclick="copilotTab('models',this)">Models &amp; Features</div>
        <div class="copilot-tab" onclick="copilotTab('license',this)">License Optimization</div>
        <div class="copilot-tab" onclick="copilotTab('anomalies',this)">Anomalies <span style="background:var(--danger);color:#fff;border-radius:10px;padding:0 5px;font-size:10px;font-weight:600;margin-left:4px">3</span></div>
      </div>

      <!-- OVERVIEW -->
      <div id="ct-overview" class="copilot-pane active">
        <div style="background:rgba(248,81,73,0.08);border:1px solid rgba(248,81,73,0.3);border-radius:6px;padding:14px 16px;margin-bottom:20px;display:flex;align-items:flex-start;gap:12px">
          <svg width="16" height="16" fill="var(--danger)" viewBox="0 0 16 16" style="flex-shrink:0;margin-top:2px"><path d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0114.082 15H1.918a1.75 1.75 0 01-1.543-2.575zm1.763.707a.25.25 0 00-.44 0L1.698 13.132a.25.25 0 00.22.368h12.164a.25.25 0 00.22-.368zM9 11a1 1 0 11-2 0 1 1 0 012 0zM8 5.25a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0V6A.75.75 0 018 5.25z"/></svg>
          <div style="flex:1">
            <div style="font-weight:600;font-size:13px;color:var(--danger);margin-bottom:4px">Seat waste detected &mdash; $1,178/month in unused licenses</div>
            <div style="font-size:12px;color:var(--fg-muted)"><strong style="color:var(--fg)">38 inactive seats</strong> (30+ days no activity) + <strong style="color:var(--fg)">24 never-used seats</strong> = <strong style="color:var(--danger)">62 of 200 seats</strong> producing no value. At $19/seat/month: <strong style="color:var(--danger)">$1,178/month ($14,136/year)</strong>.</div>
          </div>
          <button class="btn btn-sm btn-danger" style="flex-shrink:0">Export inactive list</button>
        </div>
        <div class="metric-strip">
          <div class="metric"><div class="metric-val">28.5%</div><div class="metric-lbl">Acceptance rate (7d avg)</div><div class="metric-delta up">&#8679; 1.2pp vs prev 7d</div></div>
          <div class="metric"><div class="metric-val">142 / 200</div><div class="metric-lbl">Active / total seats</div><div class="metric-delta neutral">71% utilization</div></div>
          <div class="metric" style="border-color:rgba(248,81,73,0.4)"><div class="metric-val" style="color:var(--danger)">62</div><div class="metric-lbl">Inactive + never used</div><div class="metric-delta down">$1,178/mo cost</div></div>
          <div class="metric"><div class="metric-val">4,821</div><div class="metric-lbl">Lines accepted (today)</div><div class="metric-delta up">&#8679; 12% vs 7d avg</div></div>
          <div class="metric"><div class="metric-val">312</div><div class="metric-lbl">Chat turns (today)</div><div class="metric-delta neutral">&#8212; steady</div></div>
          <div class="metric"><div class="metric-val">44</div><div class="metric-lbl">PR summaries (today)</div><div class="metric-delta up">&#8679; 8 vs 7d avg</div></div>
        </div>
        <div class="grid-2" style="margin-bottom:20px">
          <div class="chart-wrap">
            <div class="chart-title">Acceptance rate &mdash; 7-day rolling avg <span style="color:var(--fg-subtle);font-weight:400">(smooths weekends &amp; holidays)</span></div>
            <svg width="100%" height="110" viewBox="0 0 400 90" preserveAspectRatio="none">
              <defs><linearGradient id="gr-acc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#bc8cff" stop-opacity=".25"/><stop offset="100%" stop-color="#bc8cff" stop-opacity="0"/></linearGradient></defs>
              <polygon points="0,65 28,60 56,55 84,62 112,50 140,42 168,46 196,40 224,52 252,36 280,32 308,44 336,38 364,42 400,36 400,90 0,90" fill="url(#gr-acc)"/>
              <polyline points="0,65 28,60 56,55 84,62 112,50 140,42 168,46 196,40 224,52 252,36 280,32 308,44 336,38 364,42 400,36" fill="none" stroke="#bc8cff" stroke-width="2"/>
              <line x1="0" y1="45" x2="400" y2="45" stroke="#3fb950" stroke-width="1" stroke-dasharray="6,3" opacity=".5"/>
              <text x="2" y="43" font-size="9" fill="#3fb950">25% good</text>
              <text x="2" y="88" font-size="9" fill="#6e7681">Jan 1</text><text x="355" y="88" font-size="9" fill="#6e7681">Mar 10</text>
            </svg>
          </div>
          <div class="chart-wrap">
            <div class="chart-title">Seat utilization trend</div>
            <svg width="100%" height="110" viewBox="0 0 400 90" preserveAspectRatio="none">
              <polyline points="0,50 50,48 100,44 150,40 200,36 250,30 300,26 350,22 400,20" fill="none" stroke="#58a6ff" stroke-width="2"/>
              <polyline points="0,28 50,30 100,33 150,36 200,42 250,46 300,50 350,52 400,54" fill="none" stroke="#d29922" stroke-width="1.5"/>
              <polyline points="0,60 50,62 100,62 150,64 200,66 250,64 300,62 350,60 400,58" fill="none" stroke="#f85149" stroke-width="1.5"/>
              <text x="5" y="88" font-size="9" fill="#6e7681">Oct</text><text x="185" y="88" font-size="9" fill="#6e7681">Jan</text><text x="370" y="88" font-size="9" fill="#6e7681">Mar</text>
            </svg>
            <div style="display:flex;gap:12px;margin-top:6px;font-size:11px;color:var(--fg-muted)"><span><span style="color:#58a6ff">&#9644;</span> Active</span><span><span style="color:#d29922">&#9644;</span> Inactive 30d+</span><span><span style="color:#f85149">&#9644;</span> Never used</span></div>
          </div>
        </div>
        <div class="grid-2" style="margin-bottom:20px">
          <div class="card">
            <div class="card-header">Acceptance rate by language</div>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:13px">
              <div style="display:flex;align-items:center;gap:8px"><span style="width:88px;color:var(--fg-muted)">TypeScript</span><div style="flex:1;height:8px;background:var(--canvas-inset);border-radius:4px;overflow:hidden"><div style="width:38%;height:100%;background:#3fb950;border-radius:4px"></div></div><span style="color:var(--fg-muted);width:32px;text-align:right">38%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:88px;color:var(--fg-muted)">Python</span><div style="flex:1;height:8px;background:var(--canvas-inset);border-radius:4px;overflow:hidden"><div style="width:34%;height:100%;background:#3fb950;border-radius:4px"></div></div><span style="color:var(--fg-muted);width:32px;text-align:right">34%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:88px;color:var(--fg-muted)">Go</span><div style="flex:1;height:8px;background:var(--canvas-inset);border-radius:4px;overflow:hidden"><div style="width:29%;height:100%;background:#26a641;border-radius:4px"></div></div><span style="color:var(--fg-muted);width:32px;text-align:right">29%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:88px;color:var(--fg-muted)">Java</span><div style="flex:1;height:8px;background:var(--canvas-inset);border-radius:4px;overflow:hidden"><div style="width:21%;height:100%;background:#d29922;border-radius:4px"></div></div><span style="color:var(--fg-muted);width:32px;text-align:right">21%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:88px;color:var(--fg-muted)">C++</span><div style="flex:1;height:8px;background:var(--canvas-inset);border-radius:4px;overflow:hidden"><div style="width:14%;height:100%;background:#f85149;border-radius:4px"></div></div><span style="color:var(--fg-muted);width:32px;text-align:right">14%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:88px;color:var(--fg-muted)">Rust</span><div style="flex:1;height:8px;background:var(--canvas-inset);border-radius:4px;overflow:hidden"><div style="width:11%;height:100%;background:#f85149;border-radius:4px"></div></div><span style="color:var(--fg-muted);width:32px;text-align:right">11%</span></div>
            </div>
          </div>
          <div class="card">
            <div class="card-header">Correlation insight</div>
            <div style="font-size:12px;color:var(--fg-muted);margin-bottom:12px">Copilot adoption vs. delivery outcomes &mdash; correlation, not causation</div>
            <div style="display:flex;flex-direction:column;gap:10px;font-size:13px">
              <div style="display:flex;align-items:flex-start;gap:10px;padding:10px;background:rgba(63,185,80,0.08);border:1px solid rgba(63,185,80,0.2);border-radius:6px"><span style="font-size:16px;line-height:1">&#8679;</span><div><div style="color:var(--success);font-weight:500">Acceptance rate &#8679; + PR cycle time &#8681;</div><div style="font-size:11px;color:var(--fg-muted);margin-top:2px">7d acceptance rate rose 18%&#8594;28%, median PR cycle time dropped 4.8h&#8594;3.2h.</div></div></div>
              <div style="display:flex;align-items:flex-start;gap:10px;padding:10px;background:rgba(88,166,255,0.06);border:1px solid rgba(88,166,255,0.15);border-radius:6px"><span style="font-size:14px;line-height:1">&#9432;</span><div><div style="color:var(--accent);font-weight:500">Active &#8800; effective</div><div style="font-size:11px;color:var(--fg-muted);margin-top:2px">Track acceptance rate + lines accepted for real value signal.</div></div></div>
            </div>
          </div>
        </div>
        <div class="section-title">Inactive seats &mdash; action required (30+ days)</div>
        <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden">
          <table>
            <thead><tr><th>User</th><th>Seat assigned</th><th>Last activity</th><th>Last editor</th><th>Days inactive</th><th>Monthly cost</th><th></th></tr></thead>
            <tbody>
              <tr><td><span class="mention">@contractor-exit1</span></td><td style="color:var(--fg-muted)">Sep 12, 2025</td><td style="color:var(--fg-muted)">Nov 3, 2025</td><td style="color:var(--fg-subtle)">vscode</td><td><span class="label label-danger">128 days</span></td><td style="color:var(--danger);font-variant-numeric:tabular-nums">$19</td><td><button class="btn btn-sm">Revoke</button></td></tr>
              <tr><td><span class="mention">@former-intern</span></td><td style="color:var(--fg-muted)">Jun 1, 2025</td><td style="color:var(--fg-muted)">Aug 31, 2025</td><td style="color:var(--fg-subtle)">jetbrains</td><td><span class="label label-danger">191 days</span></td><td style="color:var(--danger);font-variant-numeric:tabular-nums">$19</td><td><button class="btn btn-sm">Revoke</button></td></tr>
              <tr><td><span class="mention">@rarely-uses</span></td><td style="color:var(--fg-muted)">Jan 15, 2025</td><td style="color:var(--fg-muted)">Feb 8, 2026</td><td style="color:var(--fg-subtle)">vscode</td><td><span class="label label-attention">30 days</span></td><td style="color:var(--danger);font-variant-numeric:tabular-nums">$19</td><td><button class="btn btn-sm">Review</button></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ADOPTION -->
      <div id="ct-adoption" class="copilot-pane">
        <div class="adoption-grid">
          <div class="adoption-card" style="border-color:rgba(63,185,80,0.4)"><div class="tier-count" style="color:var(--success)">34</div><div class="tier-name" style="color:var(--success)">Power Users</div><div class="tier-desc">Active every day</div></div>
          <div class="adoption-card" style="border-color:rgba(88,166,255,0.4)"><div class="tier-count" style="color:var(--accent)">68</div><div class="tier-name" style="color:var(--accent)">Regular</div><div class="tier-desc">3&ndash;4 days/week</div></div>
          <div class="adoption-card" style="border-color:rgba(210,153,34,0.4)"><div class="tier-count" style="color:var(--attention)">22</div><div class="tier-name" style="color:var(--attention)">Minimal</div><div class="tier-desc">1&ndash;2 uses in 30d</div></div>
          <div class="adoption-card" style="border-color:rgba(248,81,73,0.4)"><div class="tier-count" style="color:var(--danger)">38</div><div class="tier-name" style="color:var(--danger)">Inactive</div><div class="tier-desc">Cold 30d+ (was active)</div></div>
          <div class="adoption-card" style="border-color:rgba(110,118,129,0.4)"><div class="tier-count" style="color:var(--fg-subtle)">24</div><div class="tier-name" style="color:var(--fg-subtle)">Never Used</div><div class="tier-desc">Seat assigned, zero activity</div></div>
        </div>
        <div style="height:14px;border-radius:7px;overflow:hidden;display:flex;margin-bottom:8px">
          <div style="width:17%;background:#3fb950"></div><div style="width:34%;background:#58a6ff"></div><div style="width:11%;background:#d29922"></div><div style="width:19%;background:#f85149"></div><div style="width:12%;background:#6e7681"></div><div style="flex:1;background:var(--border-muted)"></div>
        </div>
        <div style="display:flex;gap:12px;font-size:11px;color:var(--fg-muted);margin-bottom:24px">
          <span><span style="color:#3fb950">&#9644;</span> Power 34</span><span><span style="color:#58a6ff">&#9644;</span> Regular 68</span><span><span style="color:#d29922">&#9644;</span> Minimal 22</span><span><span style="color:#f85149">&#9644;</span> Inactive 38</span><span><span style="color:#6e7681">&#9644;</span> Never 24</span>
        </div>
        <div class="grid-2" style="margin-bottom:24px">
          <div class="card">
            <div class="card-header">Daily power users <span style="font-size:11px;color:var(--fg-muted);font-weight:400">&#8212; champion candidates</span></div>
            <div style="display:flex;flex-direction:column;gap:6px;font-size:13px">
              <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-muted)"><span class="mention" style="width:80px;font-size:12px">@alice</span><span style="color:var(--fg-muted);font-size:12px;flex:1">platform-team</span><span style="color:var(--success);font-size:12px">31d streak</span><span style="color:var(--fg-muted);font-size:12px">42% accept</span></div>
              <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-muted)"><span class="mention" style="width:80px;font-size:12px">@carol</span><span style="color:var(--fg-muted);font-size:12px;flex:1">platform-team</span><span style="color:var(--success);font-size:12px">28d streak</span><span style="color:var(--fg-muted);font-size:12px">37% accept</span></div>
              <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-muted)"><span class="mention" style="width:80px;font-size:12px">@david</span><span style="color:var(--fg-muted);font-size:12px;flex:1">platform-team</span><span style="color:var(--success);font-size:12px">21d streak</span><span style="color:var(--fg-muted);font-size:12px">35% accept</span></div>
              <div style="display:flex;align-items:center;gap:8px;padding:6px 0"><span class="mention" style="width:80px;font-size:12px">@tanaka</span><span style="color:var(--fg-muted);font-size:12px;flex:1">security-team</span><span style="color:var(--success);font-size:12px">19d streak</span><span style="color:var(--fg-muted);font-size:12px">29% accept</span></div>
            </div>
          </div>
          <div class="card">
            <div class="card-header">Feature adoption gaps <span style="font-size:11px;color:var(--fg-muted);font-weight:400">among active users</span></div>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:13px">
              <div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>IDE completions</span><span style="color:var(--success)">142</span></div><div style="height:6px;background:var(--canvas-inset);border-radius:3px;overflow:hidden"><div style="width:100%;height:100%;background:#3fb950;border-radius:3px"></div></div></div>
              <div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>IDE chat</span><span style="color:var(--accent)">98</span></div><div style="height:6px;background:var(--canvas-inset);border-radius:3px;overflow:hidden"><div style="width:69%;height:100%;background:#58a6ff;border-radius:3px"></div></div></div>
              <div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>github.com chat</span><span style="color:var(--accent)">61</span></div><div style="height:6px;background:var(--canvas-inset);border-radius:3px;overflow:hidden"><div style="width:43%;height:100%;background:#58a6ff;border-radius:3px"></div></div></div>
              <div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>PR summaries (CCR) <span class="label label-attention" style="font-size:10px;height:15px">low</span></span><span style="color:var(--attention)">44</span></div><div style="height:6px;background:var(--canvas-inset);border-radius:3px;overflow:hidden"><div style="width:31%;height:100%;background:#d29922;border-radius:3px"></div></div></div>
              <div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>CLI <span class="label label-attention" style="font-size:10px;height:15px">low</span></span><span style="color:var(--attention)">18</span></div><div style="height:6px;background:var(--canvas-inset);border-radius:3px;overflow:hidden"><div style="width:13%;height:100%;background:#d29922;border-radius:3px"></div></div></div>
              <div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>Knowledge bases <span class="label label-done" style="font-size:10px;height:15px">Enterprise</span></span><span style="color:var(--done)">12</span></div><div style="height:6px;background:var(--canvas-inset);border-radius:3px;overflow:hidden"><div style="width:8%;height:100%;background:#bc8cff;border-radius:3px"></div></div></div>
            </div>
          </div>
        </div>
        <div class="section-title">CCR impact on PR review time</div>
        <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:0;margin-bottom:20px;align-items:stretch">
          <div style="background:rgba(63,185,80,0.08);border:1px solid rgba(63,185,80,0.25);border-radius:6px 0 0 6px;padding:20px;text-align:center">
            <div style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--success);letter-spacing:.05em;margin-bottom:8px">Repos WITH CCR enabled</div>
            <div style="font-size:36px;font-weight:600;color:var(--success);font-variant-numeric:tabular-nums">2.8h</div>
            <div style="font-size:12px;color:var(--fg-muted);margin-top:4px">median PR review time</div>
            <div style="font-size:11px;color:var(--fg-muted);margin-top:2px">14 repos &middot; 847 PRs</div>
          </div>
          <div style="display:flex;align-items:center;justify-content:center;padding:0 16px;background:var(--canvas-subtle);border-top:1px solid var(--border);border-bottom:1px solid var(--border)">
            <div style="text-align:center"><div style="font-size:20px;font-weight:600;color:var(--success)">&#8681; 41%</div><div style="font-size:11px;color:var(--fg-muted)">faster</div></div>
          </div>
          <div style="background:rgba(110,118,129,0.08);border:1px solid var(--border);border-radius:0 6px 6px 0;padding:20px;text-align:center">
            <div style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--fg-muted);letter-spacing:.05em;margin-bottom:8px">Repos WITHOUT CCR</div>
            <div style="font-size:36px;font-weight:600;color:var(--fg);font-variant-numeric:tabular-nums">4.7h</div>
            <div style="font-size:12px;color:var(--fg-muted);margin-top:4px">median PR review time</div>
            <div style="font-size:11px;color:var(--fg-muted);margin-top:2px">32 repos &middot; 1,203 PRs</div>
          </div>
        </div>
        <div style="font-size:12px;color:var(--fg-muted);margin-bottom:24px">&#9432; Correlation only. Repos with CCR may already have more senior reviewers or simpler PRs.</div>
        <div class="section-title">Minimal users &mdash; license-keeper risk</div>
        <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden">
          <table>
            <thead><tr><th>User</th><th>Team</th><th>Uses (30d)</th><th>Accepted</th><th>Last feature</th><th>Action</th></tr></thead>
            <tbody>
              <tr><td><span class="mention">@perf-test-user</span></td><td style="color:var(--fg-muted)">platform-team</td><td>3</td><td>1</td><td style="color:var(--fg-muted)">IDE completions</td><td><button class="btn btn-sm">Schedule onboarding</button></td></tr>
              <tr><td><span class="mention">@qa-lead</span></td><td style="color:var(--fg-muted)">security-team</td><td>2</td><td>0</td><td style="color:var(--fg-muted)">IDE completions</td><td><button class="btn btn-sm">Schedule onboarding</button></td></tr>
              <tr><td><span class="mention">@part-timer</span></td><td style="color:var(--fg-muted)">frontend-team</td><td>1</td><td>0</td><td style="color:var(--fg-muted)">Web chat</td><td><button class="btn btn-sm">Review seat need</button></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- MODELS & FEATURES -->
      <div id="ct-models" class="copilot-pane">
        <div class="grid-2" style="margin-bottom:20px">
          <div class="card">
            <div class="card-header">Model usage spread <span style="font-size:11px;color:var(--fg-muted);font-weight:400">interactions this month</span></div>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:13px">
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">GPT-4o</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:42%;height:100%;background:#58a6ff;border-radius:5px"></div></div><span style="color:var(--fg-muted);width:36px;text-align:right">42%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">Claude 3.7 Sonnet</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:31%;height:100%;background:#bc8cff;border-radius:5px"></div></div><span style="color:var(--fg-muted);width:36px;text-align:right">31%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">o3-mini</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:15%;height:100%;background:#26a641;border-radius:5px"></div></div><span style="color:var(--fg-muted);width:36px;text-align:right">15%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">acme-base <span class="label label-done" style="font-size:10px;height:15px">custom</span></span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:8%;height:100%;background:#d29922;border-radius:5px"></div></div><span style="color:var(--fg-muted);width:36px;text-align:right">8%</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">GPT-4o-mini</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:4%;height:100%;background:#6e7681;border-radius:5px"></div></div><span style="color:var(--fg-muted);width:36px;text-align:right">4%</span></div>
            </div>
            <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border);font-size:12px;color:var(--fg-muted)">Custom model <strong>acme-base</strong> at 8%&mdash;consider promoting to teams doing code review and test generation</div>
          </div>
          <div class="card">
            <div class="card-header">Feature usage spread <span style="font-size:11px;color:var(--fg-muted);font-weight:400">unique engaged users</span></div>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:13px">
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">IDE completions</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:100%;height:100%;background:#3fb950;border-radius:5px"></div></div><span style="color:var(--success);width:36px;text-align:right">142</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">IDE chat</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:69%;height:100%;background:#58a6ff;border-radius:5px"></div></div><span style="color:var(--accent);width:36px;text-align:right">98</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">github.com chat</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:43%;height:100%;background:#58a6ff;border-radius:5px"></div></div><span style="color:var(--accent);width:36px;text-align:right">61</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">PR summaries (CCR)</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:31%;height:100%;background:#d29922;border-radius:5px"></div></div><span style="color:var(--attention);width:36px;text-align:right">44</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">Copilot CLI</span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:13%;height:100%;background:#d29922;border-radius:5px"></div></div><span style="color:var(--attention);width:36px;text-align:right">18</span></div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:140px;color:var(--fg-muted);font-size:12px">Knowledge bases <span class="label label-done" style="font-size:10px;height:15px">Ent</span></span><div style="flex:1;height:10px;background:var(--canvas-inset);border-radius:5px;overflow:hidden"><div style="width:8%;height:100%;background:#bc8cff;border-radius:5px"></div></div><span style="color:var(--done);width:36px;text-align:right">12</span></div>
            </div>
          </div>
        </div>
        <div class="section-title">Editor breakdown</div>
        <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px">
          <div class="card" style="text-align:center;padding:14px 10px"><div style="font-size:26px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--accent)">112</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">VS Code</div><div style="font-size:11px;color:var(--fg-subtle)">79% of active</div></div>
          <div class="card" style="text-align:center;padding:14px 10px"><div style="font-size:26px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--accent)">38</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">JetBrains</div><div style="font-size:11px;color:var(--fg-subtle)">27% of active</div></div>
          <div class="card" style="text-align:center;padding:14px 10px"><div style="font-size:26px;font-weight:600;font-variant-numeric:tabular-nums">8</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">Neovim</div><div style="font-size:11px;color:var(--fg-subtle)">6% of active</div></div>
          <div class="card" style="text-align:center;padding:14px 10px"><div style="font-size:26px;font-weight:600;font-variant-numeric:tabular-nums">4</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">Visual Studio</div><div style="font-size:11px;color:var(--fg-subtle)">3% of active</div></div>
          <div class="card" style="text-align:center;padding:14px 10px"><div style="font-size:26px;font-weight:600;font-variant-numeric:tabular-nums">61</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">github.com</div><div style="font-size:11px;color:var(--fg-subtle)">chat &amp; PR</div></div>
        </div>
        <div class="section-title">PR summary usage by repository (CCR)</div>
        <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden">
          <table>
            <thead><tr><th>Repository</th><th>Engaged users</th><th>Summaries</th><th>Model</th><th>Avg review time</th></tr></thead>
            <tbody>
              <tr><td>acme/payments-api</td><td>18</td><td>214</td><td style="color:var(--fg-muted)">GPT-4o</td><td><span class="label label-success">2.1h</span></td></tr>
              <tr><td>acme/checkout-service</td><td>12</td><td>187</td><td style="color:var(--fg-muted)">Claude 3.7</td><td><span class="label label-success">2.4h</span></td></tr>
              <tr><td>acme/infra-deploy</td><td>4</td><td>43</td><td style="color:var(--fg-muted)">GPT-4o</td><td><span class="label label-attention">3.9h</span></td></tr>
              <tr><td>globex/auth-service</td><td>0</td><td>0</td><td style="color:var(--fg-subtle)">&#8212;</td><td><span class="label label-danger">5.8h</span></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- LICENSE OPTIMIZATION -->
      <div id="ct-license" class="copilot-pane">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:24px">
          <div class="card" style="border-color:rgba(63,185,80,0.3)"><div style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--success);letter-spacing:.04em;margin-bottom:8px">Upgrade candidates</div><div style="font-size:28px;font-weight:600;font-variant-numeric:tabular-nums">5</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">Business &#8594; Enterprise</div><div style="font-size:12px;color:var(--attention);margin-top:2px">+$100/month</div></div>
          <div class="card" style="border-color:rgba(248,81,73,0.3)"><div style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--danger);letter-spacing:.04em;margin-bottom:8px">Downgrade candidates</div><div style="font-size:28px;font-weight:600;font-variant-numeric:tabular-nums">8</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">Enterprise &#8594; Business</div><div style="font-size:12px;color:var(--success);margin-top:2px">&#8681; $160/month saved</div></div>
          <div class="card"><div style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--fg-subtle);letter-spacing:.04em;margin-bottom:8px">Net opportunity</div><div style="font-size:28px;font-weight:600;color:var(--success);font-variant-numeric:tabular-nums">&#8681;$60</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">per month after optimization</div><div style="font-size:12px;color:var(--fg-subtle);margin-top:2px">$720/year</div></div>
        </div>
        <div class="section-title" style="margin-bottom:12px">Upgrade candidates &mdash; Business &#8594; Enterprise ($19 &#8594; $39/seat)</div>
        <div style="font-size:12px;color:var(--fg-muted);margin-bottom:12px">These users consistently use Enterprise-only features but are on Business plan. Upgrading gives better access and proper API limits.</div>
        <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden;margin-bottom:24px">
          <table>
            <thead><tr><th>User</th><th>Plan</th><th>Signal</th><th>Enterprise features</th><th>Delta</th><th></th></tr></thead>
            <tbody>
              <tr><td><span class="mention">@alice</span></td><td><span class="label label-muted">Business</span></td><td>8.2 PR summaries/wk + custom model</td><td><span class="label label-done">PR summaries</span> <span class="label label-done">custom model</span></td><td style="color:var(--attention)">+$20/mo</td><td><button class="btn btn-sm btn-primary">Upgrade</button></td></tr>
              <tr><td><span class="mention">@david</span></td><td><span class="label label-muted">Business</span></td><td>Knowledge base daily</td><td><span class="label label-done">knowledge bases</span></td><td style="color:var(--attention)">+$20/mo</td><td><button class="btn btn-sm btn-primary">Upgrade</button></td></tr>
              <tr><td><span class="mention">@tanaka</span></td><td><span class="label label-muted">Business</span></td><td>6.1 PR summaries/wk</td><td><span class="label label-done">PR summaries</span></td><td style="color:var(--attention)">+$20/mo</td><td><button class="btn btn-sm btn-primary">Upgrade</button></td></tr>
            </tbody>
          </table>
        </div>
        <div class="section-title" style="margin-bottom:12px">Downgrade candidates &mdash; Enterprise &#8594; Business ($39 &#8594; $19/seat)</div>
        <div style="font-size:12px;color:var(--fg-muted);margin-bottom:12px">Enterprise users with no Enterprise-only feature usage in 90 days. Downgrading saves cost without impacting their workflow.</div>
        <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden">
          <table>
            <thead><tr><th>User</th><th>Plan</th><th>Enterprise features (90d)</th><th>Last enterprise use</th><th>Saving</th><th></th></tr></thead>
            <tbody>
              <tr><td><span class="mention">@contractor2</span></td><td><span class="label label-done">Enterprise</span></td><td><span style="color:var(--fg-subtle)">none</span></td><td style="color:var(--fg-subtle)">Never</td><td style="color:var(--success)">&#8681; $20/mo</td><td><button class="btn btn-sm">Downgrade</button></td></tr>
              <tr><td><span class="mention">@legacy-admin</span></td><td><span class="label label-done">Enterprise</span></td><td><span style="color:var(--fg-subtle)">none</span></td><td style="color:var(--fg-subtle)">Jan 2 (once)</td><td style="color:var(--success)">&#8681; $20/mo</td><td><button class="btn btn-sm">Downgrade</button></td></tr>
              <tr><td><span class="mention">@new-hire-mar</span></td><td><span class="label label-done">Enterprise</span></td><td><span style="color:var(--fg-subtle)">none</span></td><td style="color:var(--fg-subtle)">Never</td><td style="color:var(--success)">&#8681; $20/mo</td><td><button class="btn btn-sm">Downgrade</button></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ANOMALIES -->
      <div id="ct-anomalies" class="copilot-pane">
        <div style="background:rgba(248,81,73,0.06);border:1px solid rgba(248,81,73,0.2);border-radius:6px;padding:10px 14px;margin-bottom:20px;font-size:12px;color:var(--fg-muted)">
          <strong style="color:var(--fg)">3 anomalies detected</strong> from the latest Copilot metrics scrape. Investigate before taking action.
        </div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:24px">
          <div style="background:var(--canvas-subtle);border:1px solid rgba(248,81,73,0.3);border-radius:6px;padding:14px 16px">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
              <div style="display:flex;align-items:flex-start;gap:10px">
                <span class="label label-danger" style="flex-shrink:0;margin-top:1px">no telemetry</span>
                <div><div style="font-weight:500;font-size:13px"><span class="mention">@eremin</span> &mdash; PR summary activity, zero IDE telemetry</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">14 PR summaries via github.com this month but zero IDE suggestions or acceptances. Possible causes: old IDE plugin, telemetry disabled, or org policy blocking telemetry.</div></div>
              </div>
              <button class="btn btn-sm" style="flex-shrink:0">Investigate</button>
            </div>
          </div>
          <div style="background:var(--canvas-subtle);border:1px solid rgba(210,153,34,0.3);border-radius:6px;padding:14px 16px">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
              <div style="display:flex;align-items:flex-start;gap:10px">
                <span class="label label-attention" style="flex-shrink:0;margin-top:1px">accept drop</span>
                <div><div style="font-weight:500;font-size:13px"><span class="mention">@bob</span> &mdash; acceptance rate dropped 17pp week-over-week</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">7d rate: <strong style="color:var(--attention)">14%</strong> (was 31% prior week, &minus;17pp). Could indicate model change, shift to complex code domains, or unfamiliar language.</div></div>
              </div>
              <button class="btn btn-sm" style="flex-shrink:0">View detail</button>
            </div>
          </div>
          <div style="background:var(--canvas-subtle);border:1px solid rgba(210,153,34,0.3);border-radius:6px;padding:14px 16px">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
              <div style="display:flex;align-items:flex-start;gap:10px">
                <span class="label label-attention" style="flex-shrink:0;margin-top:1px">telemetry off</span>
                <div><div style="font-weight:500;font-size:13px"><span class="mention">@perf-test-user</span> &mdash; editor recorded, zero suggestions received</div><div style="font-size:12px;color:var(--fg-muted);margin-top:4px">Last activity editor: vscode/1.87.0. No suggestions or chat turns in 30 days despite active seat status. Telemetry may be disabled.</div></div>
              </div>
              <button class="btn btn-sm" style="flex-shrink:0">View detail</button>
            </div>
          </div>
        </div>
        <div class="section-title">All detected anomalies</div>
        <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden">
          <table>
            <thead><tr><th>User</th><th>Flag</th><th>Detected</th><th>Details</th><th>Status</th></tr></thead>
            <tbody>
              <tr><td><span class="mention">@eremin</span></td><td><span class="label label-danger">no_telemetry</span></td><td style="color:var(--fg-muted)">Mar 25, 2026</td><td style="color:var(--fg-muted)">PRU activity, zero IDE telemetry</td><td><span class="label label-muted">open</span></td></tr>
              <tr><td><span class="mention">@bob</span></td><td><span class="label label-attention">acceptance_drop</span></td><td style="color:var(--fg-muted)">Mar 24, 2026</td><td style="color:var(--fg-muted)">&minus;17pp week-over-week</td><td><span class="label label-muted">open</span></td></tr>
              <tr><td><span class="mention">@perf-test-user</span></td><td><span class="label label-attention">telemetry_disabled</span></td><td style="color:var(--fg-muted)">Mar 22, 2026</td><td style="color:var(--fg-muted)">Editor recorded, 0 suggestions</td><td><span class="label label-muted">open</span></td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>
  </div>
"""

target = os.path.join(os.path.dirname(__file__), '..', 'mockups', 'index.html')
with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '  <!-- ===== COPILOT INSIGHTS ===== -->'
end_marker = '\n  <!-- ===== REPORTS ===== -->'

start = content.find(start_marker)
end = content.find(end_marker)

if start == -1 or end == -1:
    print(f"ERROR: markers not found start={start} end={end}", file=sys.stderr)
    sys.exit(1)

new_content = content[:start] + NEW_COPILOT + content[end:]
with open(target, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"SUCCESS: replaced {end - start} chars → {len(NEW_COPILOT)} chars, new total {len(new_content)} chars")
