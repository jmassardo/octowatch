import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  getUnifiedSecurity,
  getSecurityPosture,
  type UnifiedSecurityResponse,
  type SecurityPostureResponse,
} from '../../api/healthSignals';
import { listDetections } from '../../api/detections';
import type { DetectionResponse, DetectionListResponse } from '../../types/detections';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Label } from '../../components/primitives/Label';
import { formatRelative } from '../../utils/dates';
import styles from './Dashboard.module.css';

const threatColumns: ColumnDef<DetectionResponse>[] = [
  {
    key: 'severity',
    header: 'Severity',
    sortable: true,
    filterable: true,
    helpText: 'Detection severity level assigned by the rule engine.',
    render: (row) => {
      const variantMap: Record<string, 'danger' | 'severe' | 'attention' | 'success'> = {
        critical: 'danger',
        high: 'severe',
        medium: 'attention',
        low: 'success',
      };
      return <Label variant={variantMap[row.severity] ?? 'muted'}>{row.severity}</Label>;
    },
    sortValue: (row) => {
      const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
      return order[row.severity] ?? 4;
    },
    filterValue: (row) => row.severity,
  },
  {
    key: 'title',
    header: 'Title',
    sortable: true,
    filterable: true,
    helpText: 'Detection rule title that fired.',
    render: (row) => row.title,
    sortValue: (row) => row.title,
    filterValue: (row) => row.title,
  },
  {
    key: 'actor',
    header: 'Actor',
    sortable: true,
    filterable: true,
    helpText: 'GitHub user or bot that triggered the detection.',
    render: (row) => row.actor ?? '—',
    sortValue: (row) => row.actor ?? '',
    filterValue: (row) => row.actor ?? '',
  },
  {
    key: 'org',
    header: 'Org',
    sortable: true,
    filterable: true,
    helpText: 'GitHub organization where the detection occurred.',
    render: (row) => row.org ?? '—',
    sortValue: (row) => row.org ?? '',
    filterValue: (row) => row.org ?? '',
  },
  {
    key: 'triggered_at',
    header: 'Triggered At',
    sortable: true,
    filterable: false,
    helpText: 'When the detection rule was triggered.',
    render: (row) => formatRelative(row.triggered_at),
    sortValue: (row) => row.triggered_at,
  },
];

export function SecurityView() {
  const navigate = useNavigate();

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

  const {
    data: threats,
    isLoading: loadingThreats,
    isError: errorThreats,
    refetch: refetchThreats,
  } = useQuery<DetectionListResponse>({
    queryKey: ['security-view', 'threats'],
    queryFn: () => listDetections({ status: 'open', page_size: 10 }),
    staleTime: 5 * 60 * 1000,
  });

  const activeThreats = threats?.total ?? 0;

  const isLoading = loadingUnified || loadingPosture || loadingThreats;

  if (isLoading) return <Spinner />;

  return (
    <>
      {errorUnified && (
        <ErrorBanner message="Could not load security alerts" onRetry={refetchUnified} />
      )}
      {errorPosture && (
        <ErrorBanner message="Could not load security posture" onRetry={refetchPosture} />
      )}
      {errorThreats && (
        <ErrorBanner message="Could not load threat detections" onRetry={refetchThreats} />
      )}

      {/* Top row: key security metrics */}
      <div className={styles.cardGrid}>
        <MetricCard
          value={String(unified?.secret_scanning.open ?? '—')}
          label="Open secret alerts"
          helpText="Open secret scanning alerts across all organizations from unified security."
          to="/health/security"
        />
        <MetricCard
          value={String(unified?.code_scanning.open ?? '—')}
          label="Open code scanning alerts"
          helpText="Open code scanning (CodeQL) alerts across all organizations."
          to="/health/security"
        />
        <MetricCard
          value={String(unified?.dependabot.open ?? '—')}
          label="Open Dependabot alerts"
          helpText="Open Dependabot vulnerability alerts across all organizations."
          to="/health/security"
        />
        <MetricCard
          value={String(activeThreats)}
          label="Active threat detections"
          helpText="Threat detections in Open status from the detection engine."
          accent={activeThreats > 0}
          to="/threats"
        />
        <MetricCard
          value={String(posture?.repos_with_ghas ?? '—')}
          label="GHAS enabled repos"
          helpText="Repositories with GitHub Advanced Security enabled."
          to="/posture"
        />
      </div>

      {/* Middle: recent threat activity */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Threat Activity</div>
        <DataTable
          columns={threatColumns}
          data={[...(threats?.items ?? [])]}
          rowKey={(row) => row.id}
          onRowClick={(row) => navigate(`/threats?id=${row.id}`)}
          emptyMessage="No open threats"
        />
      </div>

      {/* Bottom: security feature coverage */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Security Feature Coverage</div>
        <div className={styles.cardGrid}>
          <MetricCard
            value={String(posture?.repos_with_secret_scanning ?? '—')}
            label="Secret scanning enabled"
            helpText="Repositories with secret scanning enabled."
            to="/posture"
          />
          <MetricCard
            value={String(posture?.repos_with_codeql ?? '—')}
            label="CodeQL enabled"
            helpText="Repositories with CodeQL code scanning enabled."
            to="/posture"
          />
          <MetricCard
            value={String(posture?.repos_with_dependabot ?? '—')}
            label="Dependabot enabled"
            helpText="Repositories with Dependabot security updates enabled."
            to="/posture"
          />
          <MetricCard
            value={String(posture?.repos_with_ghas ?? '—')}
            label="GHAS enabled"
            helpText="Repositories with GitHub Advanced Security license enabled."
            to="/posture"
          />
          <MetricCard
            value={String(posture?.features_disabled_count ?? '—')}
            label="Features disabled"
            helpText="Count of security features that have been disabled across repos."
            accent={(posture?.features_disabled_count ?? 0) > 0}
            to="/posture"
          />
        </div>
      </div>
    </>
  );
}
