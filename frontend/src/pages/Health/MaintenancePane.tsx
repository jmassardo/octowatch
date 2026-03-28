import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getStalePrs, getUnhealthyHooks, getSkippedWorkflows } from '../../api/healthSignals';
import styles from './MaintenancePane.module.css';

export function MaintenancePane() {
  const {
    data: stalePrData,
    isLoading: isLoadingPrs,
    isError: isPrError,
    refetch: refetchPrs,
  } = useQuery({
    queryKey: ['health', 'stale-prs'],
    queryFn: () => getStalePrs(),
    staleTime: 60_000,
  });

  const {
    data: hookData,
    isLoading: isLoadingHooks,
    isError: isHookError,
    refetch: refetchHooks,
  } = useQuery({
    queryKey: ['health', 'unhealthy-hooks'],
    queryFn: () => getUnhealthyHooks(),
    staleTime: 60_000,
  });

  const {
    data: wfData,
    isLoading: isLoadingWfs,
    isError: isWfError,
    refetch: refetchWfs,
  } = useQuery({
    queryKey: ['health', 'skipped-workflows'],
    queryFn: () => getSkippedWorkflows(),
    staleTime: 60_000,
  });

  const stalePrs = stalePrData?.stale_prs ?? [];
  const unhealthyHooks = hookData?.unhealthy_hooks ?? [];
  const skippedWorkflows = wfData?.skipped_workflows ?? [];

  const isLoading = isLoadingPrs || isLoadingHooks || isLoadingWfs;

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spinner size={28} />
      </div>
    );
  }

  return (
    <>
      <div className={styles.grid2}>
        {/* Stale PRs */}
        <Card>
          <CardHeader>
            Stale PRs{' '}
            <span style={{ fontSize: 11, color: 'var(--fg-muted)', fontWeight: 400 }}>
              open &gt; configured threshold
            </span>
          </CardHeader>
          {isPrError && (
            <ErrorBanner message="Failed to load stale PRs" onRetry={() => void refetchPrs()} />
          )}
          {!isPrError && stalePrs.length === 0 && (
            <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
              No stale PRs detected
            </div>
          )}
          {!isPrError && stalePrs.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
              {stalePrs.map((pr) => (
                <div key={`${pr.org}/${pr.repo}-${pr.pr_number}`} className={styles.stalePrItem}>
                  <div>
                    <strong>{pr.org}/{pr.repo}</strong>
                    <div className={styles.stalePrTitle}>
                      #{pr.pr_number} · &quot;{pr.title}&quot;
                    </div>
                  </div>
                  <Label variant={pr.days_open > 90 ? 'danger' : 'attention'}>
                    {pr.days_open} days open
                  </Label>
                </div>
              ))}
            </div>
          )}
          <div
            className={styles.sourceNote}
            style={{ paddingTop: 8, marginTop: 8, borderTop: '1px solid var(--border-muted)' }}
          >
            ℹ️ Derived from <code className={styles.sourceCode}>pull_request.open</code> /{' '}
            <code className={styles.sourceCode}>close</code> events; no-activity staleness from
            event gaps
          </div>
        </Card>

        {/* Unhealthy webhooks */}
        <Card>
          <CardHeader>Unhealthy webhooks &amp; apps</CardHeader>
          {isHookError && (
            <ErrorBanner message="Failed to load webhook data" onRetry={() => void refetchHooks()} />
          )}
          {!isHookError && unhealthyHooks.length === 0 && (
            <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
              No unhealthy webhooks detected
            </div>
          )}
          {!isHookError && unhealthyHooks.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
              {unhealthyHooks.map((wh, idx) => {
                const isDestroy = wh.action.includes('destroy');
                const variantClass = isDestroy
                  ? styles.webhookItemDanger
                  : styles.webhookItemMuted;
                const displayName = wh.app_name || wh.hook_id || wh.action;
                return (
                  <div key={`${wh.action}-${idx}`} className={`${styles.webhookItem} ${variantClass}`}>
                    <div className={styles.webhookName}>{displayName}</div>
                    <div className={styles.webhookDetail}>
                      {wh.action} · {wh.org}/{wh.repo} · by {wh.actor}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div
            className={styles.sourceNote}
            style={{ paddingTop: 8, marginTop: 8, borderTop: '1px solid var(--border-muted)' }}
          >
            ℹ️ Derived from <code className={styles.sourceCode}>hook.*</code>,{' '}
            <code className={styles.sourceCode}>integration.*</code>, and{' '}
            <code className={styles.sourceCode}>oauth_access.*</code> audit events
          </div>
        </Card>
      </div>

      {/* Disabled / skipped workflows */}
      <div className={styles.sectionTitle}>Disabled / consistently-skipped workflows</div>
      {isWfError && (
        <ErrorBanner message="Failed to load workflow data" onRetry={() => void refetchWfs()} />
      )}
      {!isWfError && skippedWorkflows.length === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
          No disabled or skipped workflows detected
        </div>
      )}
      {!isWfError && skippedWorkflows.length > 0 && (
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Workflow</th>
                <th>Repository</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {skippedWorkflows.map((wf, idx) => (
                <tr key={`${wf.org}/${wf.repo}-${wf.workflow_name}-${idx}`}>
                  <td>{wf.workflow_name || '(unnamed)'}</td>
                  <td>{wf.org}/{wf.repo}</td>
                  <td>
                    <Label variant={wf.action.includes('disable') ? 'danger' : 'attention'}>
                      {wf.action.includes('disable') ? 'disabled' : 'deleted'}
                    </Label>
                  </td>
                  <td style={{ color: 'var(--fg-muted)' }}>{wf.actor}</td>
                  <td style={{ color: 'var(--fg-muted)' }}>
                    {new Date(wf.created_at).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className={styles.sourceNote}>
        ℹ️ Derived from{' '}
        <code className={styles.sourceCode}>workflows.disable_workflow</code>,{' '}
        <code className={styles.sourceCode}>workflows.delete_workflow</code> events
      </div>
    </>
  );
}
