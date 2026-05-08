import { useNavigate } from 'react-router-dom';
import type { StatPillFormat } from './statPillRegistry';
import styles from './StatPill.module.css';

export interface StatPillProps {
  id: string;
  icon: string;
  label: string;
  value: number | string;
  format?: StatPillFormat;
  trend?: number;
  variant?: 'default' | 'success' | 'warning' | 'danger';
  path?: string;
  isLoading?: boolean;
  hasError?: boolean;
}

function formatCount(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value);
}

function formatPercentage(value: number): string {
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)}%`;
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)}m`;
  if (minutes < 24 * 60) return `${(minutes / 60).toFixed(1).replace(/\.0$/, '')}h`;
  return `${(minutes / (24 * 60)).toFixed(1).replace(/\.0$/, '')}d`;
}

function formatValue(value: number | string, format: StatPillFormat): string {
  if (typeof value === 'string') return value;
  switch (format) {
    case 'count':
      return formatCount(value);
    case 'percentage':
      return formatPercentage(value);
    case 'duration':
      return formatDuration(value);
    case 'number':
    default:
      return formatNumber(value);
  }
}

export function StatPill({
  id,
  icon,
  label,
  value,
  format = 'number',
  trend,
  variant = 'default',
  path,
  isLoading = false,
  hasError = false,
}: StatPillProps) {
  const navigate = useNavigate();
  const displayValue = isLoading ? '…' : hasError ? '—' : formatValue(value, format);
  const trendLabel =
    trend == null ? null : `${trend > 0 ? '↑' : trend < 0 ? '↓' : '→'} ${Math.abs(trend).toFixed(1).replace(/\.0$/, '')}%`;

  function handleActivate() {
    if (path) navigate(path);
  }

  return (
    <div
      className={[
        styles.pill,
        styles[variant],
        path && styles.clickable,
        isLoading && styles.loading,
        hasError && styles.error,
      ]
        .filter(Boolean)
        .join(' ')}
      onClick={path ? handleActivate : undefined}
      onKeyDown={
        path
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleActivate();
              }
            }
          : undefined
      }
      role={path ? 'button' : undefined}
      tabIndex={path ? 0 : undefined}
      aria-label={path ? `${label}: ${displayValue}` : undefined}
      data-testid={`stat-pill-${id}`}
    >
      <span className={styles.icon} aria-hidden="true">
        {icon}
      </span>
      <div className={styles.content}>
        <span className={styles.label}>{label}</span>
        <div className={styles.valueRow}>
          <span className={styles.value}>{displayValue}</span>
          {!isLoading && !hasError && trendLabel && (
            <span
              className={[styles.trend, trend != null && trend < 0 ? styles.trendDown : styles.trendUp]
                .filter(Boolean)
                .join(' ')}
            >
              {trendLabel}
            </span>
          )}
        </div>
      </div>
      {path && (
        <span className={styles.arrow} aria-hidden="true">
          →
        </span>
      )}
    </div>
  );
}
