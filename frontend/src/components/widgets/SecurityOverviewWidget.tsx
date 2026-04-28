import { useNavigate } from 'react-router-dom';
import { Card, CardHeader } from '../primitives/Card';
import type { DetectionResponse } from '../../types/detections';

interface DetectionRowProps {
  label: string;
  count: number;
  maxCount: number;
  color: string;
  onClick: () => void;
}

function DetectionRow({ label, count, maxCount, color, onClick }: DetectionRowProps) {
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
      aria-label={`${count} ${label} — click to view details`}
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
          width: 140,
          fontSize: 12,
          color: '#8b949e',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}
        title={label}
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

  // Group detections by rule_id, using rule_name as display label
  const grouped = new Map<number, { name: string; count: number }>();
  for (const d of detections) {
    const existing = grouped.get(d.rule_id);
    if (existing) {
      existing.count += 1;
    } else {
      grouped.set(d.rule_id, {
        name: d.rule_name ?? `Rule #${d.rule_id}`,
        count: 1,
      });
    }
  }

  const rows = [...grouped.entries()]
    .map(([ruleId, { name, count }]) => ({ ruleId, name, count }))
    .sort((a, b) => b.count - a.count);

  const maxCount = rows.length > 0 ? Math.max(...rows.map((r) => r.count)) : 1;

  const barColors = [
    'var(--accent, #58a6ff)',
    'var(--done, #a371f7)',
    'var(--attention, #d29922)',
    'var(--success, #3fb950)',
    'var(--severe, #db6d28)',
    'var(--danger, #f85149)',
  ];

  return (
    <Card>
      <CardHeader>Security Overview</CardHeader>
      <div style={{ padding: '8px 8px 12px' }}>
        {rows.length === 0 ? (
          <div style={{ color: '#8b949e', fontSize: 13, padding: '12px 8px', textAlign: 'center' }}>
            No active detections
          </div>
        ) : (
          <>
            <div style={{ fontSize: 12, color: '#8b949e', padding: '0 8px 8px', fontWeight: 600 }}>
              Active detections by rule
            </div>
            {rows.map((row, i) => (
              <DetectionRow
                key={row.ruleId}
                label={row.name}
                count={row.count}
                maxCount={maxCount}
                color={barColors[i % barColors.length]}
                onClick={() => navigate(`/threats?rule_id=${row.ruleId}`)}
              />
            ))}
          </>
        )}
      </div>
    </Card>
  );
}
