import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getPosture } from '../../api/posture';
import type { PostureResponse, PostureCheckResult } from '../../api/posture';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Posture.module.css';

/* ── Helpers ───────────────────────────────────────────────────────── */

function scoreClass(score: number) {
  if (score >= 80) return styles.good;
  if (score >= 50) return styles.warn;
  return styles.bad;
}

function scoreColor(score: number) {
  if (score >= 80) return 'var(--success)';
  if (score >= 50) return 'var(--attention)';
  return 'var(--danger)';
}

function sevVariant(sev: string) {
  if (sev === 'critical') return 'danger' as const;
  if (sev === 'high') return 'severe' as const;
  if (sev === 'medium') return 'attention' as const;
  if (sev === 'info') return 'muted' as const;
  return 'success' as const;
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function boolDisplay(val: boolean | null | undefined, trueLabel = 'Enabled', falseLabel = 'Disabled') {
  if (val === null || val === undefined) return 'Unknown';
  return val ? trueLabel : falseLabel;
}

/* ── Score Gauge ───────────────────────────────────────────────────── */

function ScoreGauge({ score, label }: { score: number; label: string }) {
  return (
    <div className={`${styles.scoreGauge} ${scoreClass(score)}`}>
      <span className={styles.scoreValue}>{Math.round(score)}</span>
      <span className={styles.scoreLabel}>{label}</span>
    </div>
  );
}

/* ── Breadcrumb ────────────────────────────────────────────────────── */

function Breadcrumb({ items }: { items: PostureResponse['breadcrumb'] }) {
  return (
    <div className={styles.breadcrumb}>
      {items.map((item, i) => (
        <span key={i}>
          {i > 0 && <span className={styles.breadcrumbSep}> / </span>}
          {item.href ? <Link to={item.href}>{item.label}</Link> : <strong>{item.label}</strong>}
        </span>
      ))}
    </div>
  );
}

/* ── Check row ─────────────────────────────────────────────────────── */

function CheckRow({ check, navigate }: { check: PostureCheckResult; navigate: (path: string) => void }) {
  const passing = check.status === 'pass';
  return (
    <div
      className={styles.checkRow}
      role={check.detection_id ? 'button' : undefined}
      tabIndex={check.detection_id ? 0 : undefined}
      onClick={() => check.detection_id && navigate(`/threats`)}
      onKeyDown={(e) => {
        if (check.detection_id && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          navigate(`/threats`);
        }
      }}
    >
      <span className={`${styles.checkIcon} ${passing ? styles.checkPass : styles.checkFail}`}>
        {passing ? '✓' : '✕'}
      </span>
      <div className={styles.checkInfo}>
        <span className={styles.checkTitle}>{check.title}</span>
        {!passing && check.description && (
          <span className={styles.checkDesc}>{check.description}</span>
        )}
      </div>
      <div className={styles.checkMeta}>
        <Label variant={sevVariant(check.severity)}>{check.severity}</Label>
        {passing
          ? <Label variant="success">Passing</Label>
          : <Label variant={sevVariant(check.severity)}>{check.status}</Label>
        }
      </div>
    </div>
  );
}

/* ── Filter bar ────────────────────────────────────────────────────── */

function Filters({
  severity, setSeverity, statusFilter, setStatusFilter, showVisibility, visibility, setVisibility,
}: {
  severity: string; setSeverity: (v: string) => void;
  statusFilter: string; setStatusFilter: (v: string) => void;
  showVisibility?: boolean;
  visibility?: string; setVisibility?: (v: string) => void;
}) {
  return (
    <div className={styles.filters}>
      <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
        <option value="">All severities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
        <option value="info">Info</option>
      </select>
      <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
        <option value="">All statuses</option>
        <option value="fail">Failing</option>
        <option value="pass">Passing</option>
      </select>
      {showVisibility && setVisibility && (
        <select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
          <option value="">All visibility</option>
          <option value="public">Public</option>
          <option value="private">Private</option>
          <option value="internal">Internal</option>
        </select>
      )}
    </div>
  );
}

function filterChecks(checks: PostureCheckResult[], severity: string, statusFilter: string) {
  let filtered = checks;
  if (severity) filtered = filtered.filter((c) => c.severity === severity);
  if (statusFilter === 'pass') filtered = filtered.filter((c) => c.status === 'pass');
  if (statusFilter === 'fail') filtered = filtered.filter((c) => c.status !== 'pass');
  return filtered;
}

/* ── Enterprise View ───────────────────────────────────────────────── */

function EnterpriseView({ data }: { data: PostureResponse }) {
  const navigate = useNavigate();
  const [severity, setSeverity] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const orgs = data.orgs ?? [];

  const filteredOrgs = orgs.filter((o) => {
    if (statusFilter === 'fail' && o.score >= 80) return false;
    if (statusFilter === 'pass' && o.score < 80) return false;
    return true;
  });

  return (
    <>
      <div className={styles.header}>
        <ScoreGauge score={data.score} label="Score" />
        <div className={styles.headerInfo}>
          <div className={styles.headerTitle}>Enterprise Security Posture</div>
          <div className={styles.headerSub}>
            {orgs.length} org{orgs.length !== 1 ? 's' : ''} · Last synced {formatTime(data.last_sync_at)}
          </div>
        </div>
      </div>
      <div className={styles.content}>
        <Filters severity={severity} setSeverity={setSeverity} statusFilter={statusFilter} setStatusFilter={setStatusFilter} />
        <div className={styles.orgGrid}>
          {filteredOrgs.map((org) => (
            <div key={org.org_login} className={styles.orgCard} onClick={() => navigate(`/posture/${org.org_login}`)}>
              <div className={styles.orgCardHeader}>
                <span className={styles.orgName}>{org.org_login}</span>
                <span className={styles.orgMiniScore} style={{ color: scoreColor(org.score) }}>
                  {Math.round(org.score)}
                </span>
              </div>
              <div className={styles.scoreBar}>
                <div className={styles.scoreBarFill} style={{ width: `${org.score}%`, background: scoreColor(org.score) }} />
              </div>
              <div className={styles.orgMeta}>
                {org.repo_summary && (
                  <>
                    <span>{org.repo_summary.total} repos</span>
                    {org.repo_summary.failing > 0 && <span style={{ color: 'var(--danger)' }}>{org.repo_summary.failing} failing</span>}
                    {org.repo_summary.warning > 0 && <span style={{ color: 'var(--attention)' }}>{org.repo_summary.warning} warning</span>}
                    <span style={{ color: 'var(--success)' }}>{org.repo_summary.passing} passing</span>
                  </>
                )}
              </div>
              {severity && (
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--fg-muted)' }}>
                  {org.checks.filter((c) => c.severity === severity && c.status !== 'pass').length} {severity} finding(s)
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Top findings across enterprise */}
        {(() => {
          const allChecks = orgs.flatMap((o) => o.checks.filter((c) => c.status !== 'pass'));
          const sorted = allChecks
            .filter((c) => !severity || c.severity === severity)
            .sort((a, b) => {
              const w: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
              return (w[a.severity] ?? 5) - (w[b.severity] ?? 5);
            });
          if (!sorted.length) return null;
          return (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Top Findings</div>
              <div className={styles.checkList}>
                {sorted.slice(0, 20).map((c, i) => <CheckRow key={`${c.rule_id}-${i}`} check={c} navigate={navigate} />)}
              </div>
            </div>
          );
        })()}
      </div>
    </>
  );
}

/* ── Org View ──────────────────────────────────────────────────────── */

function OrgView({ data }: { data: PostureResponse }) {
  const navigate = useNavigate();
  const org = data.org!;
  const [severity, setSeverity] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [visibility, setVisibility] = useState('');
  const [sortCol, setSortCol] = useState<'name' | 'score' | 'visibility'>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const toggleSort = (col: typeof sortCol) => {
    if (sortCol === col) setSortDir((d) => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir(col === 'score' ? 'asc' : 'asc'); }
  };

  const checks = filterChecks(org.checks, severity, statusFilter);
  let repos = org.repos ?? [];
  if (visibility) repos = repos.filter((r) => r.visibility === visibility);
  repos = [...repos].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1;
    if (sortCol === 'score') return (a.score - b.score) * dir;
    if (sortCol === 'visibility') return (a.visibility ?? '').localeCompare(b.visibility ?? '') * dir;
    return a.repo_name.localeCompare(b.repo_name) * dir;
  });

  return (
    <>
      <div className={styles.header}>
        <ScoreGauge score={org.score} label="Score" />
        <div className={styles.headerInfo}>
          <div className={styles.headerTitle}>{org.org_login}</div>
          <div className={styles.headerSub}>
            {(org.repos ?? []).length} repos · Last synced {formatTime(data.last_sync_at)}
          </div>
        </div>
      </div>
      <div className={styles.content}>
        {/* Org metadata */}
        <div className={styles.metaCard}>
          <div className={styles.metaGrid}>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>2FA Required</div>
              <div className={styles.metaValue}>{boolDisplay(org.two_factor_required, 'Required', 'Not Required')}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Default Repo Permission</div>
              <div className={styles.metaValue}>{org.default_repo_permission ?? 'Unknown'}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Private Fork</div>
              <div className={styles.metaValue}>{boolDisplay(org.members_can_fork_private_repos, 'Allowed', 'Blocked')}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Public Repo Creation</div>
              <div className={styles.metaValue}>{boolDisplay(org.members_can_create_public_repos, 'Allowed', 'Blocked')}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>IP Allow List</div>
              <div className={styles.metaValue}>{boolDisplay(org.ip_allow_list_enabled)}</div>
            </div>
          </div>
        </div>

        {/* Org-level checks */}
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Organization Security Checks</div>
          <Filters severity={severity} setSeverity={setSeverity} statusFilter={statusFilter} setStatusFilter={setStatusFilter} />
          <div className={styles.checkList}>
            {checks.map((c, i) => <CheckRow key={`${c.rule_id}-${i}`} check={c} navigate={navigate} />)}
            {checks.length === 0 && <div className={styles.empty}>No checks match filters</div>}
          </div>
        </div>

        {/* Repos table */}
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Repositories</div>
          <Filters
            severity="" setSeverity={() => {}}
            statusFilter="" setStatusFilter={() => {}}
            showVisibility visibility={visibility} setVisibility={setVisibility}
          />
          <table className={styles.repoTable}>
            <thead>
              <tr>
                <th onClick={() => toggleSort('name')}>Repository {sortCol === 'name' ? (sortDir === 'asc' ? '↑' : '↓') : ''}</th>
                <th onClick={() => toggleSort('score')}>Score {sortCol === 'score' ? (sortDir === 'asc' ? '↑' : '↓') : ''}</th>
                <th onClick={() => toggleSort('visibility')}>Visibility {sortCol === 'visibility' ? (sortDir === 'asc' ? '↑' : '↓') : ''}</th>
                <th>Checks</th>
                <th>Detections</th>
              </tr>
            </thead>
            <tbody>
              {repos.map((r) => {
                const failing = r.checks.filter((c) => c.status !== 'pass').length;
                const passing = r.checks.filter((c) => c.status === 'pass').length;
                return (
                  <tr key={r.repo_name} onClick={() => navigate(`/posture/${r.org}/${r.repo_name}`)}>
                    <td>
                      <span className={styles.repoName}>{r.repo_name}</span>
                      {r.archived && <span style={{ marginLeft: 6 }}><Label variant="muted">archived</Label></span>}
                      {r.fork && <span style={{ marginLeft: 6 }}><Label variant="muted">fork</Label></span>}
                    </td>
                    <td>
                      <span style={{ color: scoreColor(r.score), fontWeight: 600 }}>{Math.round(r.score)}</span>
                    </td>
                    <td><Label variant={r.visibility === 'public' ? 'attention' : 'muted'}>{r.visibility ?? '—'}</Label></td>
                    <td>
                      <span style={{ color: 'var(--success)' }}>{passing}✓</span>
                      {failing > 0 && <span style={{ color: 'var(--danger)', marginLeft: 6 }}>{failing}✕</span>}
                    </td>
                    <td>{r.detection_count || '—'}</td>
                  </tr>
                );
              })}
              {repos.length === 0 && (
                <tr><td colSpan={5} className={styles.empty}>No repositories found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

/* ── Repo View ─────────────────────────────────────────────────────── */

function RepoView({ data }: { data: PostureResponse }) {
  const navigate = useNavigate();
  const repo = data.repo!;
  const [severity, setSeverity] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const checks = filterChecks(repo.checks, severity, statusFilter);

  return (
    <>
      <div className={styles.header}>
        <ScoreGauge score={repo.score} label="Score" />
        <div className={styles.headerInfo}>
          <div className={styles.headerTitle}>{repo.repo_name}</div>
          <div className={styles.headerSub}>
            {repo.org} · Last synced {formatTime(data.last_sync_at)}
          </div>
        </div>
      </div>
      <div className={styles.content}>
        {/* Repo metadata */}
        <div className={styles.metaCard}>
          <div className={styles.metaGrid}>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Visibility</div>
              <div className={styles.metaValue}>{repo.visibility ?? 'Unknown'}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Default Branch</div>
              <div className={styles.metaValue}>{repo.default_branch ?? '—'}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Language</div>
              <div className={styles.metaValue}>{repo.language ?? '—'}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Last Push</div>
              <div className={styles.metaValue}>{formatTime(repo.pushed_at)}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Archived</div>
              <div className={styles.metaValue}>{repo.archived ? 'Yes' : 'No'}</div>
            </div>
            <div className={styles.metaItem}>
              <div className={styles.metaLabel}>Fork</div>
              <div className={styles.metaValue}>{repo.fork ? 'Yes' : 'No'}</div>
            </div>
          </div>
        </div>

        {/* All checks */}
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Security Checks</div>
          <Filters severity={severity} setSeverity={setSeverity} statusFilter={statusFilter} setStatusFilter={setStatusFilter} />
          <div className={styles.checkList}>
            {checks.map((c, i) => <CheckRow key={`${c.rule_id}-${i}`} check={c} navigate={navigate} />)}
            {checks.length === 0 && <div className={styles.empty}>No checks match filters</div>}
          </div>
        </div>
      </div>
    </>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────── */

export function PosturePage() {
  const { org, repo } = useParams<{ org?: string; repo?: string }>();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['posture', org ?? '', repo ?? ''],
    queryFn: () => getPosture({ org, repo }),
  });

  if (isLoading) return <div className={styles.loading}><Spinner /></div>;
  if (isError || !data) return <div className={styles.content}><ErrorBanner message="Failed to load posture data" onRetry={refetch} /></div>;

  return (
    <div className={styles.page}>
      <Breadcrumb items={data.breadcrumb} />
      {data.level === 'enterprise' && <EnterpriseView data={data} />}
      {data.level === 'org' && <OrgView data={data} />}
      {data.level === 'repo' && <RepoView data={data} />}
    </div>
  );
}
