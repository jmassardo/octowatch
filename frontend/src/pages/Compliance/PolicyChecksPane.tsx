import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { getPolicyChecks, runPolicyChecks } from '../../api/compliance';
import type { PolicyCheckResult } from '../../types/compliance';
import styles from './Compliance.module.css';

interface PolicyChecksPaneProps {
  org?: string;
}

const policyColumns: ColumnDef<PolicyCheckResult>[] = [
  {
    key: 'display_name',
    header: 'Check',
    sortable: true,
    filterable: true,
    render: (row) => row.display_name,
    sortValue: (row) => row.display_name,
    filterValue: (row) => row.display_name,
  },
  {
    key: 'status',
    header: 'Status',
    sortable: true,
    render: (row) => (
      <Label variant={row.status === 'pass' ? 'success' : 'danger'}>
        {row.status === 'pass' ? 'Pass' : 'Fail'}
      </Label>
    ),
    sortValue: (row) => row.status,
  },
  {
    key: 'scope',
    header: 'Scope',
    sortable: true,
    render: (row) => (
      <Label variant="muted">{row.scope === 'org' ? 'Organization' : 'Repository'}</Label>
    ),
    sortValue: (row) => row.scope,
  },
  {
    key: 'last_checked',
    header: 'Last Checked',
    sortable: true,
    render: (row) => new Date(row.last_checked).toLocaleString(),
    sortValue: (row) => row.last_checked,
  },
  {
    key: 'details',
    header: 'Details',
    render: (row) => row.details,
    filterable: true,
    filterValue: (row) => row.details,
  },
];

export function PolicyChecksPane({ org }: PolicyChecksPaneProps) {
  const queryClient = useQueryClient();

  const {
    data: checks,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['compliance', 'policy-checks', org],
    queryFn: () => getPolicyChecks(org),
    staleTime: 120_000,
  });

  const runMutation = useMutation({
    mutationFn: () => runPolicyChecks(org),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance', 'policy-checks'] });
    },
  });

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
        <Spinner size={28} />
      </div>
    );
  }

  if (error || !checks) {
    return <ErrorBanner message="Failed to load policy checks" onRetry={() => refetch()} />;
  }

  return (
    <div>
      <div className={styles.actionsBar}>
        <Button
          variant="primary"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
        >
          {runMutation.isPending ? 'Running…' : 'Run All Checks'}
        </Button>
      </div>

      {/* Summary stats */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{checks.checks_passing}</div>
          <div className={styles.statLabel}>Passing</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{checks.checks_total - checks.checks_passing}</div>
          <div className={styles.statLabel}>Failing</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{checks.checks_total}</div>
          <div className={styles.statLabel}>Total Checks</div>
        </div>
      </div>

      <DataTable<PolicyCheckResult>
        columns={policyColumns}
        data={checks.checks}
        rowKey={(row) => row.check_name}
        emptyMessage="No policy checks found"
      />

      {checks.last_run && (
        <div style={{ fontSize: '0.8rem', color: 'var(--fg-muted)', marginTop: '0.75rem' }}>
          Last run: {new Date(checks.last_run).toLocaleString()}
        </div>
      )}
    </div>
  );
}
