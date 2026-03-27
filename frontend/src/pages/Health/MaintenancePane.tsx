import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { STALE_PRS, UNHEALTHY_WEBHOOKS, SKIPPED_WORKFLOWS } from './healthData';
import styles from './MaintenancePane.module.css';

export function MaintenancePane() {
  return (
    <>
      <SampleDataBanner message="Maintenance signals shown below use sample data derived from audit log event patterns. Connect your audit log source for real signals." />

      <div className={styles.grid2}>
        {/* Stale PRs */}
        <Card>
          <CardHeader>
            Stale PRs{' '}
            <span style={{ fontSize: 11, color: 'var(--fg-muted)', fontWeight: 400 }}>
              open &gt; configured threshold
            </span>
          </CardHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
            {STALE_PRS.map((pr) => (
              <div key={`${pr.repo}-${pr.number}`} className={styles.stalePrItem}>
                <div>
                  <strong>{pr.repo}</strong>
                  <div className={styles.stalePrTitle}>
                    #{pr.number} · &quot;{pr.title}&quot;
                  </div>
                </div>
                <Label variant={pr.daysOpen > 90 ? 'danger' : 'attention'}>
                  {pr.daysOpen} days open
                </Label>
              </div>
            ))}
          </div>
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
            {UNHEALTHY_WEBHOOKS.map((wh) => {
              const variantClass =
                wh.severity === 'danger'
                  ? styles.webhookItemDanger
                  : wh.severity === 'attention'
                    ? styles.webhookItemWarn
                    : styles.webhookItemMuted;
              return (
                <div key={wh.name} className={`${styles.webhookItem} ${variantClass}`}>
                  <div className={styles.webhookName}>{wh.name}</div>
                  <div className={styles.webhookDetail}>
                    {wh.detail.split('·').map((segment, i) => {
                      const trimmed = segment.trim();
                      if (wh.severity === 'danger' && i > 0) {
                        return (
                          <span key={i}>
                            {i > 0 ? ' · ' : ''}
                            <span style={{ color: 'var(--danger)' }}>{trimmed}</span>
                          </span>
                        );
                      }
                      if (wh.severity === 'attention' && trimmed.startsWith('Scopes:')) {
                        return (
                          <span key={i}>
                            Scopes:{' '}
                            <span style={{ color: 'var(--danger)' }}>
                              {trimmed.replace('Scopes: ', '')}
                            </span>
                          </span>
                        );
                      }
                      return (
                        <span key={i}>
                          {i > 0 ? ' · ' : ''}
                          {trimmed}
                        </span>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
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
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Workflow</th>
              <th>Repository</th>
              <th>Status</th>
              <th>Last run</th>
              <th>Consecutive skips</th>
            </tr>
          </thead>
          <tbody>
            {SKIPPED_WORKFLOWS.map((wf) => (
              <tr key={`${wf.repository}-${wf.workflow}`}>
                <td>{wf.workflow}</td>
                <td>{wf.repository}</td>
                <td>
                  <Label variant={wf.status === 'disabled' ? 'danger' : 'attention'}>
                    {wf.status}
                  </Label>
                </td>
                <td style={{ color: 'var(--fg-muted)' }}>{wf.lastRun}</td>
                <td>
                  {wf.consecutiveSkips != null ? (
                    <Label
                      variant={wf.consecutiveSkips >= 30 ? 'danger' : 'attention'}
                    >
                      {wf.consecutiveSkips} consecutive
                    </Label>
                  ) : (
                    <span style={{ color: 'var(--fg-muted)' }}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.sourceNote}>
        ℹ️ Derived from{' '}
        <code className={styles.sourceCode}>workflows.disabled_intentionally</code>,{' '}
        <code className={styles.sourceCode}>workflow_run</code> conclusion ={' '}
        <code className={styles.sourceCode}>skipped</code> events
      </div>
    </>
  );
}
