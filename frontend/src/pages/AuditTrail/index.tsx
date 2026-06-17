import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '../../components/common/PageHeader';
import { Card } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { listAuditLog, exportAuditLogCsv } from '../../api/auditLog';
import { usePermissions } from '../../hooks/usePermissions';
import { formatAbsolute } from '../../utils/dates';
import styles from './AuditTrail.module.css';

interface FilterState {
  actor: string;
  action: string;
  resourceType: string;
  outcome: string;
  startDate: string;
  endDate: string;
}

const INITIAL_FILTERS: FilterState = {
  actor: '',
  action: '',
  resourceType: '',
  outcome: '',
  startDate: '',
  endDate: '',
};

const PAGE_SIZE = 50;

function buildApiParams(filters: FilterState): {
  actor?: string;
  action?: string;
  resource_type?: string;
  outcome?: string;
  start_date?: string;
  end_date?: string;
} {
  const start_date = filters.startDate ? `${filters.startDate}T00:00:00Z` : undefined;
  const end_date = filters.endDate ? `${filters.endDate}T23:59:59Z` : undefined;

  return {
    actor: filters.actor || undefined,
    action: filters.action || undefined,
    resource_type: filters.resourceType || undefined,
    outcome: filters.outcome || undefined,
    start_date,
    end_date,
  };
}

function formatDetails(details: Record<string, unknown> | null): string {
  if (!details) return '-';
  try {
    return JSON.stringify(details);
  } catch {
    return '[unavailable]';
  }
}

export function AuditTrailPage() {
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const [page, setPage] = useState(1);
  const [draftFilters, setDraftFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);

  const canView = hasPermission('audit_log', 'view');
  const canExport = hasPermission('audit_log', 'export');

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin-audit-log', page, filters],
    queryFn: () =>
      listAuditLog({
        page,
        page_size: PAGE_SIZE,
        ...buildApiParams(filters),
      }),
    enabled: canView,
  });

  const handleApplyFilters = () => {
    setPage(1);
    setFilters({ ...draftFilters });
  };

  const handleResetFilters = () => {
    setPage(1);
    setDraftFilters(INITIAL_FILTERS);
    setFilters(INITIAL_FILTERS);
  };

  const handleExport = () => {
    exportAuditLogCsv(buildApiParams(filters));
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="Audit Trail"
        description="Track administrative actions and configuration changes across OctoWatch."
      />

      {permissionsLoading ? <Spinner /> : null}

      {!permissionsLoading && !canView ? (
        <ErrorBanner message="You do not have permission to view the audit trail." />
      ) : null}

      {canView ? (
        <Card>
          <div className={styles.filters}>
            <div className={styles.filterGrid}>
              <label className={styles.filterField}>
                <span>Actor</span>
                <input
                  value={draftFilters.actor}
                  onChange={(e) => setDraftFilters((prev) => ({ ...prev, actor: e.target.value }))}
                  placeholder="e.g. octocat"
                />
              </label>

              <label className={styles.filterField}>
                <span>Action</span>
                <input
                  value={draftFilters.action}
                  onChange={(e) => setDraftFilters((prev) => ({ ...prev, action: e.target.value }))}
                  placeholder="e.g. settings.*"
                />
              </label>

              <label className={styles.filterField}>
                <span>Resource Type</span>
                <input
                  value={draftFilters.resourceType}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, resourceType: e.target.value }))
                  }
                  placeholder="e.g. settings"
                />
              </label>

              <label className={styles.filterField}>
                <span>Outcome</span>
                <select
                  value={draftFilters.outcome}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, outcome: e.target.value }))
                  }
                >
                  <option value="">All outcomes</option>
                  <option value="success">success</option>
                  <option value="denied">denied</option>
                  <option value="error">error</option>
                </select>
              </label>

              <label className={styles.filterField}>
                <span>Start Date</span>
                <input
                  type="date"
                  value={draftFilters.startDate}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, startDate: e.target.value }))
                  }
                />
              </label>

              <label className={styles.filterField}>
                <span>End Date</span>
                <input
                  type="date"
                  value={draftFilters.endDate}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, endDate: e.target.value }))
                  }
                />
              </label>
            </div>

            <div className={styles.filterActions}>
              <Button size="sm" variant="primary" onClick={handleApplyFilters}>
                Apply Filters
              </Button>
              <Button size="sm" onClick={handleResetFilters}>
                Reset
              </Button>
              <Button size="sm" onClick={handleExport} disabled={!canExport}>
                Export CSV
              </Button>
            </div>
          </div>

          {isLoading ? <Spinner /> : null}
          {isError ? (
            <ErrorBanner message="Failed to load audit trail" onRetry={() => refetch()} />
          ) : null}

          {data && (
            <>
              <div className={styles.summary}>
                Showing {(data.page - 1) * data.page_size + 1}-
                {Math.min(data.page * data.page_size, data.total)} of {data.total}
              </div>

              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th scope="col">Timestamp</th>
                      <th scope="col">Actor</th>
                      <th scope="col">Action</th>
                      <th scope="col">Resource</th>
                      <th scope="col">Outcome</th>
                      <th scope="col">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.length === 0 ? (
                      <tr>
                        <td colSpan={6} className={styles.emptyRow}>
                          No audit events found for current filters.
                        </td>
                      </tr>
                    ) : (
                      data.items.map((item) => (
                        <tr key={item.id}>
                          <td>{formatAbsolute(item.timestamp)}</td>
                          <td>{item.actor}</td>
                          <td>{item.action}</td>
                          <td>
                            {item.resource_type || '-'}
                            {item.resource_id ? `:${item.resource_id}` : ''}
                          </td>
                          <td>
                            <span
                              className={`${styles.outcomeBadge} ${styles[`outcome_${item.outcome}`] ?? ''}`}
                            >
                              {item.outcome}
                            </span>
                          </td>
                          <td className={styles.detailsCell} title={formatDetails(item.details)}>
                            {formatDetails(item.details)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div className={styles.pagination}>
                <Button
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  Previous
                </Button>
                <span>Page {data.page}</span>
                <Button size="sm" onClick={() => setPage((p) => p + 1)} disabled={!data.has_more}>
                  Next
                </Button>
              </div>
            </>
          )}
        </Card>
      ) : null}
    </div>
  );
}
