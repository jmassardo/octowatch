import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { BarChart } from '../../components/charts/BarChart';
import { DrilldownDrawer } from '../../components/primitives/DrilldownDrawer';
import { Drawer } from '../../components/primitives/Drawer';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { getRepoHealth } from '../../api/healthSignals';
import type { StaleRepo, ArchivedRepo, AbandonedFork } from '../../api/healthSignals';
import { formatDateOnly } from '../../utils/dates';
import styles from './RepoHealthPane.module.css';

/* ---------- helpers ---------- */

type HealthLevel = 'critical' | 'high' | 'medium' | 'good';

function classifyRepoHealth(daysSinceActivity: number): HealthLevel {
  if (daysSinceActivity > 365) return 'critical';
  if (daysSinceActivity > 180) return 'high';
  if (daysSinceActivity > 90) return 'medium';
  return 'good';
}

function healthLabelVariant(level: HealthLevel) {
  switch (level) {
    case 'critical':
      return 'danger' as const;
    case 'high':
      return 'severe' as const;
    case 'medium':
      return 'attention' as const;
    case 'good':
      return 'success' as const;
  }
}

function formatDaysAgo(days: number): string {
  if (days === 0) return 'Today';
  if (days === 1) return '1 day';
  return `${days} days`;
}

/**
 * Build a 6-bucket monthly breakdown from stale repos for the trend chart.
 * Each bucket counts how many repos crossed the staleness threshold (90 days)
 * in that month based on last_event_at + 90 days.
 */
function buildStaleTrend(stale: StaleRepo[]): { labels: string[]; counts: number[] } {
  const now = new Date();
  const labels: string[] = [];
  const counts: number[] = [];
  const monthNames = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    labels.push(`${monthNames[d.getMonth()]} ${d.getFullYear()}`);
    counts.push(0);
  }

  for (const repo of stale) {
    const becameStale = new Date(repo.last_event_at);
    becameStale.setDate(becameStale.getDate() + 90);
    const monthDiff =
      (now.getFullYear() - becameStale.getFullYear()) * 12 +
      (now.getMonth() - becameStale.getMonth());
    const idx = 5 - monthDiff;
    if (idx >= 0 && idx < 6) {
      counts[idx]++;
    }
  }

  return { labels, counts };
}

/* ---------- sub-components ---------- */

interface RepoRow {
  org: string;
  repo: string;
  daysSinceActivity: number;
  lastEventAt: string;
}

function RepoHealthTable({ repos }: { repos: RepoRow[] }) {
  const [selectedRow, setSelectedRow] = useState<RepoRow | null>(null);
  const columns: ColumnDef<RepoRow>[] = [
    {
      key: 'repository',
      header: 'Repository',
      sortable: true,
      filterable: true,
      render: (r) => (
        <>
          <div className={styles.repoName}>
            {r.org}/{r.repo}
          </div>
          <div className={styles.repoSub}>{r.org}</div>
        </>
      ),
      sortValue: (r) => `${r.org}/${r.repo}`,
      filterValue: (r) => `${r.org}/${r.repo}`,
      helpText:
        'Repository name and organization. Derived from git.push and repo.create audit events.',
    },
    {
      key: 'lastPush',
      header: 'Last push',
      sortable: true,
      render: (r) => {
        const pushVariant =
          r.daysSinceActivity > 180 ? 'danger' : r.daysSinceActivity > 30 ? 'attention' : 'success';
        return <Label variant={pushVariant}>{formatDaysAgo(r.daysSinceActivity)}</Label>;
      },
      sortValue: (r) => r.daysSinceActivity,
      helpText:
        'Days since the last git push event. Repos without pushes for 90+ days are considered stale.',
    },
    {
      key: 'overall',
      header: 'Overall',
      sortable: true,
      render: (r) => {
        const health = classifyRepoHealth(r.daysSinceActivity);
        return (
          <Label variant={healthLabelVariant(health)}>
            {health === 'critical'
              ? '⚠ critical'
              : health === 'good'
                ? 'healthy'
                : health === 'high'
                  ? '⚠ high'
                  : 'needs attention'}
          </Label>
        );
      },
      sortValue: (r) => r.daysSinceActivity,
      helpText:
        'Overall repo health classification based on days since last push activity. Critical (365+ days), High (180+), Medium (90+), Good (recent).',
    },
  ];

  return (
    <div className={styles.tableWrap}>
      <DataTable
        columns={columns}
        data={repos}
        rowKey={(r) => `${r.org}/${r.repo}`}
        emptyMessage="No stale repositories found"
        onRowClick={(row) => setSelectedRow(row)}
      />
      <div style={{ fontSize: 11, color: 'var(--fg-subtle)', padding: '8px 12px' }}>
        ℹ️ Additional repository health data (branch protection, secret scanning, Dependabot, CI)
        requires GitHub API integration.
      </div>
      <Drawer open={!!selectedRow} onClose={() => setSelectedRow(null)} title="Repository Details">
        {selectedRow && (
          <dl style={{ padding: '16px' }}>
            {Object.entries(selectedRow).map(([key, value]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <dt style={{ fontSize: '0.8em', color: 'var(--fg-muted)', marginBottom: 2 }}>
                  {key}
                </dt>
                <dd style={{ margin: 0 }}>{String(value ?? '—')}</dd>
              </div>
            ))}
          </dl>
        )}
      </Drawer>
    </div>
  );
}

function StaleTrendChart({ stale }: { stale: StaleRepo[] }) {
  const { labels, counts } = buildStaleTrend(stale);
  const allZero = counts.every((c) => c === 0);

  return (
    <div>
      <div className={styles.sectionTitle}>Stale repository trend — last 6 months</div>
      <div className={styles.sectionSub}>
        Repos with no push activity beyond the configured staleness threshold (default: 90 days).
        Derived from <code className={styles.codeSnippet}>git.push</code> and{' '}
        <code className={styles.codeSnippet}>repo.create</code> audit events.
      </div>
      {allZero ? (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: '16px 0' }}>
          No repos crossed the staleness threshold in the past 6 months.
        </div>
      ) : (
        <div className={styles.chartWrap}>
          <BarChart
            xAxisData={labels}
            series={[
              {
                name: 'Stale repos',
                data: counts,
                color: '#f85149',
              },
            ]}
            height={180}
          />
        </div>
      )}
    </div>
  );
}

function UnhealthySummaryCards({ stale }: { stale: StaleRepo[] }) {
  const [drilldown, setDrilldown] = useState<'branch-protection' | 'secret-scanning' | null>(null);

  const critical = stale.filter((r) => r.days_since_activity > 365);
  const high = stale.filter((r) => r.days_since_activity > 180 && r.days_since_activity <= 365);

  const noBranchProtection = stale.filter((r) => r.days_since_activity > 180);
  const noSecretScanning = stale.filter((r) => r.days_since_activity > 90);

  const drilldownData =
    drilldown === 'branch-protection'
      ? noBranchProtection
      : drilldown === 'secret-scanning'
        ? noSecretScanning
        : [];
  const drilldownTitle =
    drilldown === 'branch-protection' ? 'Repos inactive > 180 days' : 'Repos inactive > 90 days';

  const repoColumns: ColumnDef<StaleRepo>[] = [
    {
      key: 'repo',
      header: 'Repository',
      sortable: true,
      filterable: true,
      render: (r) => `${r.org}/${r.repo}`,
      sortValue: (r) => `${r.org}/${r.repo}`,
      filterValue: (r) => `${r.org}/${r.repo}`,
      helpText: 'Repository name and organization. Filter to focus on specific repos.',
    },
    {
      key: 'org',
      header: 'Organization',
      render: (r) => r.org,
      helpText: 'The GitHub organization that owns this repository.',
    },
    {
      key: 'last_event',
      header: 'Last Activity',
      render: (r) => formatDateOnly(r.last_event_at),
      helpText:
        'Date of the last recorded audit event for this repository. Derived from git.push and other repo-level events.',
    },
    {
      key: 'days',
      header: 'Days Inactive',
      sortable: true,
      render: (r) => String(r.days_since_activity),
      sortValue: (r) => r.days_since_activity,
      helpText:
        'Number of days since the last repository activity. Repos inactive 180+ days are candidates for archiving or deletion.',
    },
  ];

  function handleKeyDown(e: React.KeyboardEvent, target: 'branch-protection' | 'secret-scanning') {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setDrilldown(target);
    }
  }

  return (
    <div className={styles.grid2}>
      <Card>
        <CardHeader>Repos inactive &gt; 180 days</CardHeader>
        <div
          className={`${styles.bigNumber} ${styles.clickableStat}`}
          onClick={() => setDrilldown('branch-protection')}
          role="button"
          tabIndex={0}
          aria-label={`${noBranchProtection.length} repos inactive more than 180 days – click to view details`}
          onKeyDown={(e) => handleKeyDown(e, 'branch-protection')}
        >
          {noBranchProtection.length}
        </div>
        <div className={styles.cardBody}>
          {noBranchProtection
            .slice(0, 4)
            .map((r) => `${r.org}/${r.repo}`)
            .join(', ') || 'None detected'}
        </div>
        <div className={styles.cardFooter}>
          ℹ Repositories with no recorded audit-log activity in the last 180+ days. Consider
          archiving or reviewing ownership.
          {critical.length + high.length > 0 && (
            <>
              {' '}
              ({critical.length} critical, {high.length} high severity)
            </>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader>Repos inactive &gt; 90 days</CardHeader>
        <div
          className={`${styles.bigNumber} ${styles.clickableStat}`}
          onClick={() => setDrilldown('secret-scanning')}
          role="button"
          tabIndex={0}
          aria-label={`${noSecretScanning.length} repos inactive more than 90 days – click to view details`}
          onKeyDown={(e) => handleKeyDown(e, 'secret-scanning')}
        >
          {noSecretScanning.length}
        </div>
        <div className={styles.cardBody}>
          {noSecretScanning.length > 0
            ? `${Math.min(noSecretScanning.length, 3)} repos approaching staleness, ${Math.max(0, noSecretScanning.length - 3)} more in the 90–180 day range`
            : 'None detected'}
        </div>
        <div className={styles.cardFooter}>
          ℹ Repositories with no recorded audit-log activity in the last 90+ days. Derived from{' '}
          <code className={styles.codeSnippet}>git.push</code> and{' '}
          <code className={styles.codeSnippet}>repo.create</code> events.
        </div>
      </Card>
      <DrilldownDrawer
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={drilldownTitle}
        data={drilldownData}
        columns={repoColumns}
        rowKey={(r) => `${r.org}/${r.repo}`}
      />
    </div>
  );
}

function ArchiveCandidatesList({
  stale,
  archived,
  forks,
}: {
  stale: StaleRepo[];
  archived: ArchivedRepo[];
  forks: AbandonedFork[];
}) {
  const candidates = stale.filter((r) => r.days_since_activity > 180);

  return (
    <div>
      <div className={styles.sectionTitle}>Archive / delete candidates</div>
      <div className={styles.sectionSub}>
        Repositories inactive for 180+ days, recently archived repos, and abandoned forks.
      </div>

      {candidates.length === 0 && archived.length === 0 && forks.length === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16 }}>
          No archive candidates found.
        </div>
      )}

      <div className={styles.archiveList}>
        {candidates.map((r) => (
          <div key={`stale-${r.org}/${r.repo}`} className={styles.archiveItem}>
            <div>
              <div className={styles.archiveRepo}>
                {r.org}/{r.repo}
              </div>
              <div className={styles.archiveMeta}>
                No activity for {r.days_since_activity} days — consider archiving
              </div>
            </div>
            <Label variant="danger">stale {r.days_since_activity}d</Label>
          </div>
        ))}

        {archived.map((r) => (
          <div key={`arch-${r.org}/${r.repo}`} className={styles.archiveItem}>
            <div>
              <div className={styles.archiveRepo}>
                {r.org}/{r.repo}
              </div>
              <div className={styles.archiveMeta}>
                Archived {formatDateOnly(r.archived_at)} by {r.archived_by}
              </div>
            </div>
            <Label variant="muted">archived</Label>
          </div>
        ))}

        {forks.map((f) => (
          <div key={`fork-${f.org}/${f.repo}`} className={styles.archiveItem}>
            <div>
              <div className={styles.archiveRepo}>
                {f.org}/{f.repo}
              </div>
              <div className={styles.archiveMeta}>
                Forked {formatDateOnly(f.forked_at)} by {f.actor} — no activity since (
                {f.days_since_fork} days)
              </div>
            </div>
            <Label variant="attention">abandoned fork</Label>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- main pane ---------- */

export function RepoHealthPane() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['health', 'repo-health'],
    queryFn: () => getRepoHealth(),
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorBanner message="Failed to load repository health data" onRetry={() => void refetch()} />
    );
  }

  const stale = data?.stale ?? [];
  const archived = data?.archived ?? [];
  const abandonedForks = data?.abandoned_forks ?? [];

  const repos: RepoRow[] = stale.map((r) => ({
    org: r.org,
    repo: r.repo,
    daysSinceActivity: r.days_since_activity,
    lastEventAt: r.last_event_at,
  }));

  const totalRepos = repos.length;

  return (
    <div className={styles.pane}>
      <div className={styles.toolbar}>
        <span className={styles.toolbarInfo}>
          {totalRepos} {totalRepos === 1 ? 'repo' : 'repos'} · showing signals with issues
        </span>
      </div>

      <RepoHealthTable repos={repos} />

      <StaleTrendChart stale={stale} />

      <UnhealthySummaryCards stale={stale} />

      <ArchiveCandidatesList stale={stale} archived={archived} forks={abandonedForks} />
    </div>
  );
}
