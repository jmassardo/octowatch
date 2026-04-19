import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getUnifiedSecurity } from '../../api/healthSignals';
import type { UnifiedSecurityResponse } from '../../api/healthSignals';
import { Card, CardHeader } from '../primitives/Card';
import { Spinner } from '../primitives/Spinner';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { LineAreaChart } from '../charts/LineAreaChart';

/* ---------- helpers ---------- */

function SeverityBar({
  label,
  count,
  maxCount,
  color,
  onClick,
}: {
  label: string;
  count: number;
  maxCount: number;
  color: string;
  onClick?: () => void;
}) {
  const w =
    count > 0 ? `${Math.max(8, Math.round((count / Math.max(maxCount, 1)) * 100))}%` : '2px';
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '3px 0',
        cursor: onClick ? 'pointer' : undefined,
      }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={onClick ? `${count} ${label} — click to view details` : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <span style={{ width: 60, fontSize: 11, color: '#8b949e' }}>{label}</span>
      <div style={{ flex: 1, height: 8, background: '#21262d', borderRadius: 4 }}>
        <div style={{ height: '100%', background: color, borderRadius: 4, width: w }} />
      </div>
      <span style={{ width: 32, textAlign: 'right', fontSize: 12, fontWeight: 600 }}>{count}</span>
    </div>
  );
}

/* ---------- main component ---------- */

export function UnifiedSecurityWidget() {
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['health', 'unified-security'],
    queryFn: getUnifiedSecurity,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>Security Overview</CardHeader>
        <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
          <Spinner size={24} />
        </div>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardHeader>Security Overview</CardHeader>
        <ErrorBanner message="Failed to load security overview" onRetry={() => void refetch()} />
      </Card>
    );
  }

  const unified: UnifiedSecurityResponse = data;
  const ss = unified.secret_scanning;
  const cs = unified.code_scanning;
  const dep = unified.dependabot;
  const det = unified.detections;
  const trend = unified.trend_30d;

  const trendDays = trend.map((t) => t.day.slice(5)); // MM-DD
  const maxSev = Math.max(
    cs.critical + dep.critical,
    cs.high + dep.high,
    cs.medium + dep.medium,
    cs.low + dep.low,
    1,
  );

  return (
    <Card>
      <CardHeader>Security Overview</CardHeader>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          padding: '12px 16px',
        }}
      >
        {/* Secret scanning */}
        <div
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/health/security')}
          role="button"
          tabIndex={0}
          aria-label={`${ss.open} open secret alerts — view details`}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              navigate('/health/security');
            }
          }}
        >
          <div style={{ fontSize: 24, fontWeight: 700 }}>{ss.open}</div>
          <div style={{ fontSize: 11, color: '#8b949e' }}>Secret alerts</div>
        </div>

        {/* Code scanning */}
        <div
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/health/governance')}
          role="button"
          tabIndex={0}
          aria-label={`${cs.open} open code scanning alerts — view details`}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              navigate('/health/governance');
            }
          }}
        >
          <div style={{ fontSize: 24, fontWeight: 700 }}>{cs.open}</div>
          <div style={{ fontSize: 11, color: '#8b949e' }}>Code alerts</div>
        </div>

        {/* Dependabot */}
        <div
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/health/governance')}
          role="button"
          tabIndex={0}
          aria-label={`${dep.open} open Dependabot alerts — view details`}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              navigate('/health/governance');
            }
          }}
        >
          <div style={{ fontSize: 24, fontWeight: 700 }}>{dep.open}</div>
          <div style={{ fontSize: 11, color: '#8b949e' }}>Dependabot</div>
        </div>

        {/* Active detections */}
        <div
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/threats')}
          role="button"
          tabIndex={0}
          aria-label={`${det.active} active detections — view details`}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              navigate('/threats');
            }
          }}
        >
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: det.active > 0 ? 'var(--danger)' : undefined,
            }}
          >
            {det.active}
          </div>
          <div style={{ fontSize: 11, color: '#8b949e' }}>Detections</div>
        </div>
      </div>

      {/* Severity breakdown */}
      <div style={{ padding: '8px 16px' }}>
        <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 6, fontWeight: 600 }}>
          Open alerts by severity (Code + Dependabot)
        </div>
        <SeverityBar
          label="Critical"
          count={cs.critical + dep.critical}
          maxCount={maxSev}
          color="var(--danger)"
          onClick={() => navigate('/health/governance')}
        />
        <SeverityBar
          label="High"
          count={cs.high + dep.high}
          maxCount={maxSev}
          color="var(--severe, #db6d28)"
          onClick={() => navigate('/health/governance')}
        />
        <SeverityBar
          label="Medium"
          count={cs.medium + dep.medium}
          maxCount={maxSev}
          color="var(--attention, #d29922)"
          onClick={() => navigate('/health/governance')}
        />
        <SeverityBar
          label="Low"
          count={cs.low + dep.low}
          maxCount={maxSev}
          color="var(--success, #3fb950)"
          onClick={() => navigate('/health/governance')}
        />
      </div>

      {/* Critical aging signal */}
      {dep.critical_aging_gt_90d > 0 && (
        <div
          style={{
            margin: '0 16px 8px',
            padding: '8px 12px',
            background: 'rgba(248,81,73,0.1)',
            border: '1px solid rgba(248,81,73,0.3)',
            borderRadius: 6,
            fontSize: 12,
            color: 'var(--danger)',
          }}
        >
          ⚠ <strong>{dep.critical_aging_gt_90d}</strong> critical Dependabot
          {dep.critical_aging_gt_90d === 1 ? ' alert' : ' alerts'} open &gt;90 days
        </div>
      )}

      {/* 30-day trend chart */}
      {trend.length > 0 && (
        <div style={{ padding: '4px 8px 8px' }}>
          <LineAreaChart
            title="30-day alert trend"
            xAxisData={trendDays}
            series={[
              {
                name: 'Secret scanning',
                data: trend.map((t) => t.secret_scanning),
                color: '#f0883e',
                areaOpacity: 0.15,
              },
              {
                name: 'Code scanning',
                data: trend.map((t) => t.code_scanning),
                color: '#58a6ff',
                areaOpacity: 0.15,
              },
              {
                name: 'Dependabot',
                data: trend.map((t) => t.dependabot),
                color: '#bc8cff',
                areaOpacity: 0.15,
              },
            ]}
            height={140}
          />
        </div>
      )}
    </Card>
  );
}
