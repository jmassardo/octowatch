import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getTeamHealthSummary,
  getBusFactorAnalysis,
  getEngagement,
  getPolicyViolations,
  getKnowledgeConcentration,
  type BusFactorRepo,
  type PolicyViolation,
  type DeveloperTierInfo,
  type ConcentrationRisk,
} from '../../api/teamHealth';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Card, CardHeader } from '../../components/primitives/Card';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { Avatar } from '../../components/primitives/Avatar';
import { useChartColors } from '../../hooks/useChartColors';
import { formatRelativeShort } from '../../utils/dates';
import styles from './TeamHealth.module.css';

/* ── Violation type filter options ────────────────────────────────────── */

const VIOLATION_TYPES = [
  { value: 'all', label: 'All types' },
  { value: 'branch_protection_bypass', label: 'Branch protection' },
  { value: 'force_push_default_branch', label: 'Force push' },
  { value: 'admin_permission_escalation', label: 'Permission escalation' },
  { value: '2fa_disabled', label: '2FA disabled' },
  { value: 'ssh_key_added', label: 'SSH key added' },
] as const;

/* ── Main component ──────────────────────────────────────────────────── */

export function TeamHealthPane() {
  const [violationFilter, setViolationFilter] = useState('all');
  const chartColors = useChartColors();

  const {
    data: summary,
    isLoading: loadingSummary,
    isError: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['team-health', 'summary'],
    queryFn: getTeamHealthSummary,
  });

  const { data: busFactorData, isLoading: loadingBusFactor } = useQuery({
    queryKey: ['team-health', 'bus-factor'],
    queryFn: () => getBusFactorAnalysis(),
  });

  const { data: engagementData, isLoading: loadingEngagement } = useQuery({
    queryKey: ['team-health', 'engagement'],
    queryFn: () => getEngagement(),
  });

  const { data: violationsData, isLoading: loadingViolations } = useQuery({
    queryKey: ['team-health', 'policy-violations'],
    queryFn: () => getPolicyViolations(),
  });

  const { data: concentrationData } = useQuery({
    queryKey: ['team-health', 'knowledge-concentration'],
    queryFn: () => getKnowledgeConcentration(),
  });

  /* ── Derived data ──────────────────────────────────────────────────── */

  const filteredViolations = useMemo(() => {
    const violations = violationsData?.violations ?? [];
    if (violationFilter === 'all') return violations;
    return violations.filter((v) => v.type === violationFilter);
  }, [violationsData?.violations, violationFilter]);

  const dormantDevelopers = useMemo(
    () => engagementData?.tiers?.dormant ?? [],
    [engagementData?.tiers?.dormant],
  );

  const engagementTierData = useMemo(() => {
    const counts = engagementData?.counts;
    if (!counts) return [];
    const total =
      (counts.active ?? 0) +
      (counts.regular ?? 0) +
      (counts.occasional ?? 0) +
      (counts.dormant ?? 0);
    if (total === 0) return [];
    return [
      {
        tier: 'Active',
        count: counts.active,
        pct: Math.round((counts.active / total) * 100),
        color: chartColors.success,
      },
      {
        tier: 'Regular',
        count: counts.regular,
        pct: Math.round((counts.regular / total) * 100),
        color: chartColors.accent,
      },
      {
        tier: 'Occasional',
        count: counts.occasional,
        pct: Math.round((counts.occasional / total) * 100),
        color: 'var(--attention)',
      },
      {
        tier: 'Dormant',
        count: counts.dormant,
        pct: Math.round((counts.dormant / total) * 100),
        color: 'var(--danger)',
      },
    ];
  }, [chartColors.accent, chartColors.success, engagementData?.counts]);

  /* ── Loading / Error ───────────────────────────────────────────────── */

  const isLoading = loadingSummary || loadingBusFactor || loadingEngagement || loadingViolations;

  if (summaryError) {
    return <ErrorBanner message="Failed to load team health data" onRetry={refetchSummary} />;
  }

  if (isLoading) {
    return (
      <div className={styles.pane}>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  /* ── Render ─────────────────────────────────────────────────────────── */

  return (
    <div className={styles.pane}>
      {/* ── Health Indicators Strip ────────────────────────────────── */}
      <div className={styles.metricsStrip}>
        <MetricCard
          value={String(summary?.bus_factor_score ?? '—')}
          label="Bus Factor Score"
          helpText="Minimum bus factor across all repos (1=critical, 5=safe). Based on contributor concentration in the last 90 days."
          accent={summary !== undefined && summary.bus_factor_score <= 2}
        />
        <MetricCard
          value={`${summary?.active_contributors_pct ?? 0}%`}
          label="Active Contributors"
          helpText={`${summary?.engagement_counts?.active ?? 0} of ${summary?.total_developers ?? 0} developers active in last 7 days.`}
        />
        <MetricCard
          value={String(summary?.dormant_developers ?? 0)}
          label="Dormant Developers"
          helpText="Developers with no repo-related activity in the last 30 days."
        />
        <MetricCard
          value={String(summary?.policy_violations_count ?? 0)}
          label="Policy Violations (30d)"
          delta={
            summary?.policy_violations_trend === 'up'
              ? '↑ vs prev 30d'
              : summary?.policy_violations_trend === 'down'
                ? '↓ vs prev 30d'
                : undefined
          }
          deltaDir={
            summary?.policy_violations_trend === 'up'
              ? 'up'
              : summary?.policy_violations_trend === 'down'
                ? 'down'
                : 'neutral'
          }
          accent={summary !== undefined && summary.policy_violations_count > 0}
          helpText="Count of detected policy violations from audit log patterns in the last 30 days."
        />
        <MetricCard
          value={capitalizeFirst(summary?.knowledge_concentration_risk ?? 'low')}
          label="Knowledge Concentration"
          helpText="Overall risk of knowledge being concentrated in too few developers across repos."
          accent={summary?.knowledge_concentration_risk === 'high'}
        />
      </div>

      {/* ── Bus Factor Risk ───────────────────────────────────────── */}
      <div className={styles.sectionTitle}>Bus Factor Risk</div>
      <div className={styles.sectionNote}>
        Repos sorted by risk. Bus factor = minimum developers needed to maintain the codebase.
      </div>

      <Card>
        <CardHeader>Per-repo bus factor</CardHeader>
        <DataTable<BusFactorRepo>
          columns={busFactorColumns}
          data={busFactorData?.repos ?? []}
          rowKey={(r) => r.repo}
          emptyMessage="No repository data available. Push or PR events are needed to calculate bus factor."
        />
      </Card>

      {/* ── Engagement Tiers ──────────────────────────────────────── */}
      <div className={styles.sectionTitle} style={{ marginTop: 24 }}>
        Developer Engagement
      </div>
      <div className={styles.sectionNote}>
        Engagement tiers based on last activity date. Active = last 7d, Regular = 7-14d, Occasional
        = 14-30d, Dormant = 30d+.
      </div>

      {engagementTierData.length > 0 && (
        <Card>
          <CardHeader>Engagement distribution</CardHeader>
          <div className={styles.stackedBarContainer}>
            <div className={styles.stackedBar} role="img" aria-label="Engagement tier distribution">
              {engagementTierData.map((t) => (
                <div
                  key={t.tier}
                  className={styles.stackedSegment}
                  style={{ width: `${Math.max(t.pct, 1)}%`, background: t.color }}
                  title={`${t.tier}: ${t.count} (${t.pct}%)`}
                />
              ))}
            </div>
            <div className={styles.stackedLegend}>
              {engagementTierData.map((t) => (
                <span key={t.tier} className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ background: t.color }} />
                  {t.tier} ({t.count})
                </span>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* ── Engagement Trend ──────────────────────────────────────── */}
      {(engagementData?.trend ?? []).length > 0 && (
        <Card>
          <CardHeader>Monthly active developers (last 3 months)</CardHeader>
          <div className={styles.trendBars}>
            {engagementData!.trend.map((t) => {
              const maxVal = Math.max(...engagementData!.trend.map((p) => p.active_developers), 1);
              const h = Math.max(4, (t.active_developers / maxVal) * 60);
              return (
                <div key={t.month} className={styles.trendBarCol}>
                  <div
                    className={styles.trendBarFill}
                    style={{ height: h }}
                    title={`${t.month}: ${t.active_developers} developers`}
                  />
                  <span className={styles.trendBarLabel}>{t.month.slice(0, 7)}</span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* ── Dormant Developers ────────────────────────────────────── */}
      {dormantDevelopers.length > 0 && (
        <Card>
          <CardHeader>Dormant developers ({dormantDevelopers.length})</CardHeader>
          <DataTable<DeveloperTierInfo>
            columns={dormantColumns}
            data={dormantDevelopers}
            rowKey={(d) => d.login}
            emptyMessage="No dormant developers found."
          />
        </Card>
      )}

      {/* ── Policy Violations ─────────────────────────────────────── */}
      <div className={styles.sectionTitle} style={{ marginTop: 24 }}>
        Policy Violations
      </div>
      <div className={styles.sectionNote}>
        Detected policy violations from audit log event patterns in the last 30 days.
      </div>

      <div className={styles.violationFilters}>
        {VIOLATION_TYPES.map((vt) => (
          <button
            key={vt.value}
            className={[styles.filterBtn, violationFilter === vt.value && styles.filterBtnActive]
              .filter(Boolean)
              .join(' ')}
            onClick={() => setViolationFilter(vt.value)}
          >
            {vt.label}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader>Violations ({filteredViolations.length})</CardHeader>
        <DataTable<PolicyViolation>
          columns={violationColumns}
          data={filteredViolations}
          rowKey={(v) => `${v.action}-${v.actor}-${v.timestamp}`}
          emptyMessage="No policy violations detected."
        />
      </Card>

      {/* ── Knowledge Concentration ───────────────────────────────── */}
      {(concentrationData?.risks ?? []).length > 0 && (
        <>
          <div className={styles.sectionTitle} style={{ marginTop: 24 }}>
            Knowledge Concentration Risks
          </div>
          <div className={styles.sectionNote}>
            Repos where a single developer owns more than 50% of activity.
          </div>
          <Card>
            <CardHeader>High-concentration repos</CardHeader>
            <DataTable<ConcentrationRisk>
              columns={concentrationColumns}
              data={concentrationData?.risks ?? []}
              rowKey={(r) => r.repo}
              emptyMessage="No concentration risks detected."
            />
          </Card>
        </>
      )}
    </div>
  );
}

/* ── Column definitions ──────────────────────────────────────────────── */

const busFactorColumns: ColumnDef<BusFactorRepo>[] = [
  {
    key: 'repo',
    header: 'Repository',
    filterable: true,
    filterValue: (row) => row.repo,
    render: (row) => <span style={{ fontWeight: 500 }}>{row.repo}</span>,
  },
  {
    key: 'bus_factor',
    header: 'Bus Factor',
    sortable: true,
    sortValue: (row) => row.bus_factor,
    helpText: 'Number of key contributors. 1 = critical (one person knows everything).',
    render: (row) => (
      <span style={{ color: riskColor(row.risk_level), fontWeight: 600 }}>{row.bus_factor}</span>
    ),
  },
  {
    key: 'risk_level',
    header: 'Risk',
    sortable: true,
    sortValue: (row) => riskOrder(row.risk_level),
    render: (row) => (
      <span
        className={styles.riskBadge}
        style={{
          background: riskBadgeBg(row.risk_level),
          color: riskColor(row.risk_level),
        }}
      >
        {row.risk_level}
      </span>
    ),
  },
  {
    key: 'contributors',
    header: 'Top Contributors',
    render: (row) => (
      <div className={styles.avatarChips}>
        {row.top_contributors.slice(0, 4).map((c) => (
          <span key={c.login} className={styles.avatarChip} title={`@${c.login}: ${c.pct}%`}>
            <Avatar username={c.login} size={20} />
            <span className={styles.avatarChipPct}>{c.pct}%</span>
          </span>
        ))}
      </div>
    ),
  },
  {
    key: 'contributor_count',
    header: 'Contributors',
    sortable: true,
    sortValue: (row) => row.contributor_count,
    render: (row) => <>{row.contributor_count}</>,
  },
];

const dormantColumns: ColumnDef<DeveloperTierInfo>[] = [
  {
    key: 'login',
    header: 'Developer',
    filterable: true,
    filterValue: (row) => row.login,
    render: (row) => (
      <span className={styles.devLogin}>
        <Avatar username={row.login} size={20} />@{row.login}
      </span>
    ),
  },
  {
    key: 'last_active',
    header: 'Last Active',
    sortable: true,
    sortValue: (row) => (row.last_active ? new Date(row.last_active) : new Date(0)),
    render: (row) => <>{row.last_active ? formatRelativeShort(row.last_active) : 'Never'}</>,
  },
  {
    key: 'event_count',
    header: 'Total Events',
    sortable: true,
    sortValue: (row) => row.event_count,
    render: (row) => <>{row.event_count}</>,
  },
];

const violationColumns: ColumnDef<PolicyViolation>[] = [
  {
    key: 'type',
    header: 'Type',
    filterable: true,
    filterValue: (row) => row.type,
    render: (row) => <span style={{ fontWeight: 500 }}>{row.description}</span>,
  },
  {
    key: 'severity',
    header: 'Severity',
    sortable: true,
    sortValue: (row) => severityOrder(row.severity),
    render: (row) => (
      <span
        className={styles.riskBadge}
        style={{
          background: severityBadgeBg(row.severity),
          color: severityColor(row.severity),
        }}
      >
        {row.severity}
      </span>
    ),
  },
  {
    key: 'actor',
    header: 'Actor',
    filterable: true,
    filterValue: (row) => row.actor ?? '',
    render: (row) =>
      row.actor ? (
        <span className={styles.devLogin}>
          <Avatar username={row.actor} size={20} />@{row.actor}
        </span>
      ) : (
        <span style={{ color: 'var(--fg-muted)' }}>—</span>
      ),
  },
  {
    key: 'repo',
    header: 'Repository',
    filterable: true,
    filterValue: (row) => row.repo ?? '',
    render: (row) => <>{row.repo ?? '—'}</>,
  },
  {
    key: 'timestamp',
    header: 'When',
    sortable: true,
    sortValue: (row) => (row.timestamp ? new Date(row.timestamp) : new Date(0)),
    render: (row) => <>{row.timestamp ? formatRelativeShort(row.timestamp) : '—'}</>,
  },
];

const concentrationColumns: ColumnDef<ConcentrationRisk>[] = [
  {
    key: 'repo',
    header: 'Repository',
    filterable: true,
    filterValue: (row) => row.repo,
    render: (row) => <span style={{ fontWeight: 500 }}>{row.repo}</span>,
  },
  {
    key: 'top_actor',
    header: 'Top Contributor',
    render: (row) => (
      <span className={styles.devLogin}>
        <Avatar username={row.top_actor} size={20} />@{row.top_actor}
      </span>
    ),
  },
  {
    key: 'concentration_pct',
    header: 'Concentration',
    sortable: true,
    sortValue: (row) => row.concentration_pct,
    render: (row) => (
      <span style={{ color: riskColor(row.risk_level), fontWeight: 600 }}>
        {row.concentration_pct}%
      </span>
    ),
  },
  {
    key: 'risk_level',
    header: 'Risk',
    sortable: true,
    sortValue: (row) => riskOrder(row.risk_level),
    render: (row) => (
      <span
        className={styles.riskBadge}
        style={{
          background: riskBadgeBg(row.risk_level),
          color: riskColor(row.risk_level),
        }}
      >
        {row.risk_level}
      </span>
    ),
  },
  {
    key: 'recommendation',
    header: 'Recommendation',
    render: (row) => <span style={{ fontSize: 12 }}>{row.recommendation}</span>,
  },
];

/* ── Utility helpers ─────────────────────────────────────────────────── */

function capitalizeFirst(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function riskColor(level: string): string {
  switch (level) {
    case 'critical':
      return 'var(--danger)';
    case 'high':
      return 'var(--danger)';
    case 'medium':
      return 'var(--attention)';
    default:
      return '#238636';
  }
}

function riskBadgeBg(level: string): string {
  switch (level) {
    case 'critical':
      return 'rgba(248,81,73,0.15)';
    case 'high':
      return 'rgba(248,81,73,0.15)';
    case 'medium':
      return 'rgba(210,153,34,0.15)';
    default:
      return 'rgba(35,134,54,0.15)';
  }
}

function riskOrder(level: string): number {
  switch (level) {
    case 'critical':
      return 0;
    case 'high':
      return 1;
    case 'medium':
      return 2;
    default:
      return 3;
  }
}

function severityColor(s: string): string {
  switch (s) {
    case 'critical':
      return 'var(--danger)';
    case 'high':
      return 'var(--danger)';
    case 'medium':
      return 'var(--attention)';
    default:
      return 'var(--fg-muted)';
  }
}

function severityBadgeBg(s: string): string {
  return riskBadgeBg(s);
}

function severityOrder(s: string): number {
  return riskOrder(s);
}
