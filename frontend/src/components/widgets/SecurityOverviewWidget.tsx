import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { listDetections } from '../../api/detections';
import { useOrg } from '../../hooks/useOrg';
import { Card, CardHeader } from '../primitives/Card';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Spinner } from '../primitives/Spinner';
import type { DetectionResponse, DetectionSeverity } from '../../types/detections';

const SEVERITY_ORDER: DetectionSeverity[] = ['critical', 'high', 'medium', 'low'];

const SEVERITY_COLORS: Record<DetectionSeverity, string> = {
  critical: 'var(--danger, #f85149)',
  high: 'var(--severe, #db6d28)',
  medium: 'var(--attention, #d29922)',
  low: 'var(--fg-muted, #8b949e)',
};

interface SeverityRowProps {
  label: string;
  count: number;
  maxCount: number;
  color: string;
  onClick: () => void;
}

function SeverityRow({ label, count, maxCount, color, onClick }: SeverityRowProps) {
  const width =
    count > 0 ? `${Math.max(8, Math.round((count / Math.max(maxCount, 1)) * 100))}%` : '2px';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 8px',
        cursor: 'pointer',
        borderRadius: 6,
        transition: 'background 0.15s',
      }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`${count} ${label} detections — click to view`}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
      onMouseEnter={(event) => {
        (event.currentTarget as HTMLDivElement).style.background = 'rgba(177, 186, 196, 0.08)';
      }}
      onMouseLeave={(event) => {
        (event.currentTarget as HTMLDivElement).style.background = 'transparent';
      }}
    >
      <span
        style={{
          width: 70,
          fontSize: 12,
          color,
          fontWeight: 600,
          textTransform: 'capitalize',
          flexShrink: 0,
        }}
      >
        {label}
      </span>
      <div style={{ flex: 1, height: 8, background: 'var(--border-muted)', borderRadius: 4 }}>
        <div style={{ height: '100%', background: color, borderRadius: 4, width }} />
      </div>
      <span style={{ width: 32, textAlign: 'right', fontSize: 12, fontWeight: 600, flexShrink: 0 }}>
        {count}
      </span>
      <span style={{ fontSize: 10, color: 'var(--fg-muted)', marginLeft: 2 }}>→</span>
    </div>
  );
}

interface Props {
  detections?: readonly DetectionResponse[];
}

export function SecurityOverviewWidget({ detections }: Props) {
  const navigate = useNavigate();
  const { selectedOrg } = useOrg();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['widget', 'security-overview', selectedOrg],
    queryFn: () =>
      listDetections({ status: 'open', org: selectedOrg || undefined, page_size: 100 }),
    staleTime: 60_000,
    enabled: detections == null,
  });

  const resolvedDetections = detections ?? data?.items ?? [];

  if (detections == null && isLoading) {
    return (
      <Card>
        <CardHeader>Security Overview</CardHeader>
        <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
          <Spinner size={24} />
        </div>
      </Card>
    );
  }

  if (detections == null && (isError || !data)) {
    return (
      <Card>
        <CardHeader>Security Overview</CardHeader>
        <ErrorBanner message="Failed to load security overview" onRetry={() => void refetch()} />
      </Card>
    );
  }

  const bySeverity: Record<DetectionSeverity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const detection of resolvedDetections) {
    if (detection.severity in bySeverity) {
      bySeverity[detection.severity] += 1;
    }
  }

  const maxCount = Math.max(...Object.values(bySeverity), 1);
  const total = resolvedDetections.length;

  return (
    <Card>
      <CardHeader>Security Overview</CardHeader>
      <div style={{ padding: '8px 8px 12px' }}>
        {total === 0 ? (
          <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: '12px 8px', textAlign: 'center' }}>
            No active detections
          </div>
        ) : (
          <>
            <div style={{ fontSize: 12, color: 'var(--fg-muted)', padding: '0 8px 8px', fontWeight: 600 }}>
              Active detections by severity — {total} total
            </div>
            {SEVERITY_ORDER.map((severity) => (
              <SeverityRow
                key={severity}
                label={severity}
                count={bySeverity[severity]}
                maxCount={maxCount}
                color={SEVERITY_COLORS[severity]}
                onClick={() => navigate(`/threats?severity=${severity}`)}
              />
            ))}
          </>
        )}
      </div>
    </Card>
  );
}
