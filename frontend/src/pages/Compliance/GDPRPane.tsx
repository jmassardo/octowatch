import { useQuery } from '@tanstack/react-query';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getGDPRSummary } from '../../api/compliance';
import styles from './Compliance.module.css';

interface GDPRPaneProps {
  org?: string;
}

export function GDPRPane({ org }: GDPRPaneProps) {
  const {
    data: gdpr,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['compliance', 'gdpr', org],
    queryFn: () => getGDPRSummary(org),
    staleTime: 120_000,
  });

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
        <Spinner size={28} />
      </div>
    );
  }

  if (error || !gdpr) {
    return <ErrorBanner message="Failed to load GDPR data" onRetry={() => refetch()} />;
  }

  const completedChecks = gdpr.breach_notification_readiness.filter((c) => c.complete).length;
  const totalChecks = gdpr.breach_notification_readiness.length;

  return (
    <div>
      {/* Stats */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{gdpr.dsr_requests_total}</div>
          <div className={styles.statLabel}>DSR Requests Total</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{gdpr.dsr_requests_completed}</div>
          <div className={styles.statLabel}>Completed</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{gdpr.dsr_requests_pending}</div>
          <div className={styles.statLabel}>Pending</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{gdpr.erasure_requests_processed}</div>
          <div className={styles.statLabel}>Erasures Processed</div>
        </div>
      </div>

      {/* Data Processing Activities */}
      <div className={styles.gdprSection}>
        <h3 className={styles.gdprSectionTitle}>Data Processing Activities</h3>
        <div className={styles.activityList}>
          {gdpr.data_processing_activities.map((activity) => (
            <div key={activity.activity_name} className={styles.activityItem}>
              <div className={styles.activityName}>{activity.activity_name}</div>
              <div className={styles.activityMeta}>
                <span>Purpose: {activity.purpose}</span>
                <span>Legal basis: {activity.legal_basis}</span>
                <span>Retention: {activity.retention_period}</span>
                <span>Categories: {activity.data_categories.join(', ')}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Consent Tracking */}
      <div className={styles.gdprSection}>
        <h3 className={styles.gdprSectionTitle}>Consent Tracking</h3>
        <div className={styles.checklistItem}>
          <Label variant={gdpr.consent_tracking_enabled ? 'success' : 'danger'}>
            {gdpr.consent_tracking_enabled ? 'Enabled' : 'Disabled'}
          </Label>
          <span>Consent tracking status</span>
        </div>
      </div>

      {/* Data Retention */}
      <div className={styles.gdprSection}>
        <h3 className={styles.gdprSectionTitle}>Data Retention Policy</h3>
        <div className={styles.checklistItem}>
          <Label variant={gdpr.data_retention_compliant ? 'success' : 'danger'}>
            {gdpr.data_retention_compliant ? 'Compliant' : 'Non-Compliant'}
          </Label>
          <span>Data retention policy compliance</span>
        </div>
      </div>

      {/* Breach Notification Readiness */}
      <div className={styles.gdprSection}>
        <h3 className={styles.gdprSectionTitle}>
          Breach Notification Readiness ({completedChecks}/{totalChecks})
        </h3>
        {gdpr.breach_notification_readiness.map((check) => (
          <div key={check.item} className={styles.checklistItem}>
            <span
              className={check.complete ? styles.checkComplete : styles.checkIncomplete}
              aria-hidden="true"
            >
              {check.complete ? '✓' : '○'}
            </span>
            <span className={check.complete ? styles.checkComplete : styles.checkIncomplete}>
              {check.item}
            </span>
          </div>
        ))}
      </div>

      {gdpr.last_updated && (
        <div style={{ fontSize: '0.8rem', color: 'var(--fg-muted)', marginTop: '1rem' }}>
          Last updated: {new Date(gdpr.last_updated).toLocaleString()}
        </div>
      )}
    </div>
  );
}
