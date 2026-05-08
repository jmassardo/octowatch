import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMaintenanceStatus, type MaintenanceStatus } from '../../api/maintenance';
import { formatAbsolute } from '../../utils/dates';
import styles from './MaintenanceBanner.module.css';

const DEFAULT_MESSAGE = 'OctoWatch is undergoing scheduled maintenance.';

interface MaintenanceBannerProps {
  status?: MaintenanceStatus;
  polling?: boolean;
  pollIntervalMs?: number;
  dismissible?: boolean;
}

function bannerSignature(status: MaintenanceStatus | undefined) {
  if (!status) return 'none';
  return [
    status.enabled,
    status.message,
    status.severity,
    status.block_writes,
    status.started_at,
    status.estimated_end,
  ].join('|');
}

export function MaintenanceBanner({
  status: overrideStatus,
  polling = true,
  pollIntervalMs = 30_000,
  dismissible = true,
}: MaintenanceBannerProps) {
  const { data } = useQuery({
    queryKey: ['maintenance-status'],
    queryFn: getMaintenanceStatus,
    enabled: overrideStatus === undefined,
    refetchInterval: overrideStatus === undefined && polling ? pollIntervalMs : false,
    refetchOnWindowFocus: true,
  });
  const status = overrideStatus ?? data;
  const signature = useMemo(() => bannerSignature(status), [status]);
  const [dismissedSignature, setDismissedSignature] = useState<string | null>(null);

  if (!status?.enabled || dismissedSignature === signature) {
    return null;
  }

  return (
    <div
      className={`${styles.banner} ${styles[status.severity]}`}
      data-testid="maintenance-banner"
      data-severity={status.severity}
    >
      <div className={styles.content}>
        <div className={styles.titleRow}>
          <span className={styles.badge}>Maintenance</span>
          {status.block_writes && <span className={styles.action}>Write operations are temporarily disabled.</span>}
        </div>
        <p className={styles.message}>{status.message || DEFAULT_MESSAGE}</p>
        <div className={styles.meta}>
          {status.estimated_end && <span>Estimated end: {formatAbsolute(status.estimated_end)}</span>}
          {status.started_at && <span>Started: {formatAbsolute(status.started_at)}</span>}
        </div>
      </div>
      {dismissible && (
        <button
          type="button"
          className={styles.dismiss}
          aria-label="Dismiss maintenance notice"
          onClick={() => setDismissedSignature(signature)}
        >
          ×
        </button>
      )}
    </div>
  );
}
