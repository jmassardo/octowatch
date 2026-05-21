import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import {
  getClassificationSummary,
  getClassifiedUsers,
  triggerClassificationRun,
} from '../../api/userClassification';
import type { ClassifiedUser } from '../../api/userClassification';
import { PageHeader } from '../../components/common/PageHeader';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Label } from '../../components/primitives/Label';
import styles from './UserBehavior.module.css';

const PERSONA_COLORS: Record<string, string> = {
  'Power User': 'var(--done)',
  'Web UI Only': 'var(--accent)',
  'IDE Only': 'var(--success)',
  'API/CLI Only': 'var(--attention)',
  'Copilot Active': 'var(--done)',
  'Truly Dormant': 'var(--fg-subtle)',
  'Lightly Active': 'var(--fg-muted)',
  'Admin Only': 'var(--severe)',
  'CI/CD Bot': 'var(--accent)',
};

const PERSONA_VARIANTS: Record<
  string,
  'danger' | 'attention' | 'success' | 'done' | 'muted' | 'accent' | 'severe'
> = {
  'Power User': 'accent',
  'Web UI Only': 'success',
  'IDE Only': 'success',
  'API/CLI Only': 'attention',
  'Copilot Active': 'accent',
  'Truly Dormant': 'muted',
  'Lightly Active': 'muted',
  'Admin Only': 'severe',
  'CI/CD Bot': 'done',
};

const ALL_PERSONAS = [
  'Power User',
  'Web UI Only',
  'IDE Only',
  'API/CLI Only',
  'Copilot Active',
  'Truly Dormant',
  'Lightly Active',
  'Admin Only',
  'CI/CD Bot',
];

const PAGE_SIZE = 50;

export function UserBehaviorPage() {
  const queryClient = useQueryClient();
  const [personaFilter, setPersonaFilter] = useState<string>('');
  const [page, setPage] = useState(1);

  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
  } = useQuery({
    queryKey: ['user-classification', 'summary'],
    queryFn: getClassificationSummary,
    staleTime: 60_000,
  });

  const {
    data: usersData,
    isLoading: usersLoading,
    error: usersError,
  } = useQuery({
    queryKey: ['user-classification', 'users', personaFilter, page],
    queryFn: () =>
      getClassifiedUsers({
        persona: personaFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    staleTime: 30_000,
  });

  const runMutation = useMutation({
    mutationFn: () => triggerClassificationRun(90),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-classification'] });
    },
  });

  // Donut chart option
  const chartOption = useMemo(() => {
    if (!summary?.personas?.length) return null;
    const data = summary.personas.map((p) => ({
      name: p.persona,
      value: p.user_count,
    }));
    const colors = summary.personas.map((p) => PERSONA_COLORS[p.persona] ?? 'var(--fg-muted)');

    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: {
        orient: 'vertical' as const,
        right: 10,
        top: 'center',
        textStyle: { color: 'var(--chart-text)', fontSize: 12 },
      },
      series: [
        {
          type: 'pie',
          radius: ['50%', '75%'],
          center: ['35%', '50%'],
          avoidLabelOverlap: false,
          label: { show: false },
          data,
          itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: 'transparent' },
          color: colors,
        },
      ],
    };
  }, [summary]);

  // Table columns
  const columns: ColumnDef<ClassifiedUser>[] = useMemo(
    () => [
      {
        key: 'user_login',
        header: 'User',
        sortable: true,
        filterable: true,
        render: (row) => <strong>{row.user_login}</strong>,
        sortValue: (row) => row.user_login,
        filterValue: (row) => row.user_login,
      },
      {
        key: 'org',
        header: 'Org',
        sortable: true,
        filterable: true,
        render: (row) => row.org,
        sortValue: (row) => row.org,
        filterValue: (row) => row.org,
      },
      {
        key: 'persona',
        header: 'Persona',
        sortable: true,
        render: (row) => (
          <Label variant={PERSONA_VARIANTS[row.persona] ?? 'muted'}>{row.persona}</Label>
        ),
        sortValue: (row) => row.persona,
      },
      {
        key: 'confidence_score',
        header: 'Confidence',
        sortable: true,
        render: (row) => `${(row.confidence_score * 100).toFixed(0)}%`,
        sortValue: (row) => row.confidence_score,
        width: '100px',
      },
      {
        key: 'event_count',
        header: 'Events',
        sortable: true,
        render: (row) => row.event_count.toLocaleString(),
        sortValue: (row) => row.event_count,
        width: '100px',
      },
      {
        key: 'surfaces',
        header: 'Surfaces',
        render: (row) => (
          <div className={styles.surfaceList}>
            {row.surfaces.map((s) => (
              <span key={s} className={styles.surfaceTag}>
                {s}
              </span>
            ))}
          </div>
        ),
      },
      {
        key: 'classified_at',
        header: 'Classified',
        sortable: true,
        render: (row) =>
          row.classified_at ? new Date(row.classified_at).toLocaleDateString() : '—',
        sortValue: (row) => row.classified_at ?? '',
        width: '120px',
      },
    ],
    [],
  );

  const totalPages = usersData ? Math.ceil(usersData.total / PAGE_SIZE) : 0;

  const handlePersonaChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setPersonaFilter(e.target.value);
    setPage(1);
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="User Behavior"
        description="Classify users by audit log activity patterns into behavioral personas"
        actions={[
          {
            label: runMutation.isPending ? 'Running…' : 'Run Classification',
            onClick: () => runMutation.mutate(),
            variant: 'primary',
            disabled: runMutation.isPending,
          },
        ]}
      />

      {/* Key metrics */}
      {summaryLoading ? (
        <div className={styles.metricsRow}>
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
        </div>
      ) : summaryError ? (
        <div role="alert">Failed to load classification summary.</div>
      ) : (
        <div className={styles.metricsRow}>
          <div className={styles.metricCard}>
            <div className={styles.metricValue} data-testid="total-users">
              {summary?.total_users?.toLocaleString() ?? 0}
            </div>
            <div className={styles.metricLabel}>Total Classified Users</div>
          </div>
          <div className={styles.metricCard}>
            <div className={styles.metricValue} data-testid="dormant-pct">
              {summary?.dormant_pct?.toFixed(1) ?? 0}%
            </div>
            <div className={styles.metricLabel}>Dormant Users</div>
          </div>
          <div className={styles.metricCard}>
            <div className={styles.metricValue} data-testid="power-user-pct">
              {summary?.power_user_pct?.toFixed(1) ?? 0}%
            </div>
            <div className={styles.metricLabel}>Power Users</div>
          </div>
        </div>
      )}

      {/* Chart + table layout */}
      <div className={styles.chartUserRow}>
        {/* Donut chart */}
        <div className={styles.chartCard}>
          <div className={styles.chartTitle}>Persona Distribution</div>
          {summaryLoading ? (
            <SkeletonCard lines={6} />
          ) : chartOption ? (
            <ReactECharts option={chartOption} style={{ height: 240 }} opts={{ renderer: 'svg' }} />
          ) : (
            <div>No classification data yet. Run a classification to see results.</div>
          )}
        </div>

        {/* User table */}
        <div className={styles.tableCard}>
          <div className={styles.filterRow}>
            <label htmlFor="persona-filter">Filter by persona:</label>
            <select
              id="persona-filter"
              className={styles.filterSelect}
              value={personaFilter}
              onChange={handlePersonaChange}
            >
              <option value="">All Personas</option>
              {ALL_PERSONAS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          {usersLoading ? (
            <SkeletonCard lines={8} />
          ) : usersError ? (
            <div role="alert">Failed to load user classifications.</div>
          ) : (
            <>
              <DataTable
                columns={columns}
                data={usersData?.users ?? []}
                rowKey={(row) => row.id}
                emptyMessage="No classified users found. Run classification to populate results."
              />

              {totalPages > 1 && (
                <div className={styles.pagination}>
                  <button
                    type="button"
                    className={styles.paginationBtn}
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    Previous
                  </button>
                  <span>
                    Page {page} of {totalPages}
                  </span>
                  <button
                    type="button"
                    className={styles.paginationBtn}
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
