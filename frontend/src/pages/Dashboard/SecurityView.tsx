import { useQuery } from '@tanstack/react-query';
import {
  getUnifiedSecurity,
  getSecurityPosture,
  type UnifiedSecurityResponse,
  type SecurityPostureResponse,
} from '../../api/healthSignals';
import { MetricCard } from '../../components/primitives/MetricCard';
import { BarChart } from '../../components/charts/BarChart';
import { RadialGauge } from '../../components/charts/RadialGauge';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Dashboard.module.css';

export function SecurityView() {
  const {
    data: unified,
    isLoading: loadingUnified,
    isError: errorUnified,
    refetch: refetchUnified,
  } = useQuery<UnifiedSecurityResponse>({
    queryKey: ['security-view', 'unified'],
    queryFn: getUnifiedSecurity,
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: posture,
    isLoading: loadingPosture,
    isError: errorPosture,
    refetch: refetchPosture,
  } = useQuery<SecurityPostureResponse>({
    queryKey: ['security-view', 'posture'],
    queryFn: getSecurityPosture,
    staleTime: 5 * 60 * 1000,
  });

  const isLoading = loadingUnified || loadingPosture;

  if (isLoading) return <Spinner />;

  const total = posture
    ? Math.max(
        posture.repos_with_ghas,
        posture.repos_with_secret_scanning,
        posture.repos_with_codeql,
        posture.repos_with_dependabot,
        1,
      )
    : 0;

  function coveragePct(count: number | undefined): number {
    if (!count || total === 0) return 0;
    return Math.round((count / total) * 100);
  }

  const alertXAxis = ['Secret Scanning', 'Code Scanning', 'Dependabot'];
  const alertValues = [
    unified?.secret_scanning.open ?? 0,
    unified?.code_scanning.open ?? 0,
    unified?.dependabot.open ?? 0,
  ];

  return (
    <>
      {errorUnified && (
        <ErrorBanner message="Could not load security alerts" onRetry={refetchUnified} />
      )}
      {errorPosture && (
        <ErrorBanner message="Could not load security posture" onRetry={refetchPosture} />
      )}

      {/* Top row: key security metrics */}
      <div className={styles.cardGrid}>
        <MetricCard
          value={String(unified?.secret_scanning.open ?? '—')}
          label="Open secret alerts"
          helpText="Open secret scanning alerts across all organizations from unified security."
          to="/advanced-security/secrets"
        />
        <MetricCard
          value={String(unified?.code_scanning.open ?? '—')}
          label="Open code scanning alerts"
          helpText="Open code scanning (CodeQL) alerts across all organizations."
          to="/advanced-security/code"
        />
        <MetricCard
          value={String(unified?.dependabot.open ?? '—')}
          label="Open Dependabot alerts"
          helpText="Open Dependabot vulnerability alerts across all organizations."
          to="/advanced-security/dependabot"
        />
        <MetricCard
          value={String(posture?.repos_with_ghas ?? '—')}
          label="GHAS enabled repos"
          helpText="Repositories with GitHub Advanced Security enabled."
          to="/posture"
        />
      </div>

      {/* Alert Trend */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Alert Trend</div>
        <Card>
          <CardHeader>Open alerts by category</CardHeader>
          <BarChart
            xAxisData={alertXAxis}
            series={[
              {
                name: 'Open Alerts',
                data: alertValues,
              },
            ]}
            height={160}
          />
        </Card>
      </div>

      {/* Security Feature Coverage — radial gauges */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Security Feature Coverage</div>
        <div className={styles.gaugeGrid}>
          <RadialGauge
            value={coveragePct(posture?.repos_with_secret_scanning)}
            label="Secret Scanning"
          />
          <RadialGauge value={coveragePct(posture?.repos_with_codeql)} label="CodeQL" />
          <RadialGauge value={coveragePct(posture?.repos_with_dependabot)} label="Dependabot" />
          <RadialGauge value={coveragePct(posture?.repos_with_ghas)} label="GHAS" />
        </div>
      </div>
    </>
  );
}
