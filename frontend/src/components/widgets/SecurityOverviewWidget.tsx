import { useNavigate } from 'react-router-dom';
import { Card, CardHeader } from '../primitives/Card';
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
  const w =
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
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.background = 'rgba(177, 186, 196, 0.08)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.background = 'transparent';
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
      <div style={{ flex: 1, height: 8, background: '#21262d', borderRadius: 4 }}>
        <div style={{ height: '100%', background: color, borderRadius: 4, width: w }} />
      </div>
      <span style={{ width: 32, textAlign: 'right', fontSize: 12, fontWeight: 600, flexShrink: 0 }}>
        {count}
      </span>
      <span style={{ fontSize: 10, color: '#8b949e', marginLeft: 2 }}>→</span>
    </div>
  );
}

interface Props {
  detections: readonly DetectionResponse[];
}

export function SecurityOverviewWidget({ detections }: Props) {
  const navigate = useNavigate();

  const bySeverity: Record<DetectionSeverity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const d of detections) {
    if (d.severity in bySeverity) {
      bySeverity[d.severity] += 1;
    }
  }

  const maxCount = Math.max(...Object.values(bySeverity), 1);
  const total = detections.length;

  return (
    <Card>
      <CardHeader>Security Overview</CardHeader>
      <div style={{ padding: '8px 8px 12px' }}>
        {total === 0 ? (
          <div style={{ color: '#8b949e', fontSize: 13, padding: '12px 8px', textAlign: 'center' }}>
            No active detections
          </div>
        ) : (
          <>
            <div style={{ fontSize: 12, color: '#8b949e', padding: '0 8px 8px', fontWeight: 600 }}>
              Active detections by severity — {total} total
            </div>
            {SEVERITY_ORDER.map((sev) => (
              <SeverityRow
                key={sev}
                label={sev}
                count={bySeverity[sev]}
                maxCount={maxCount}
                color={SEVERITY_COLORS[sev]}
                onClick={() => navigate(`/threats?severity=${sev}`)}
              />
            ))}
          </>
        )}
      </div>
    </Card>
  );
}
