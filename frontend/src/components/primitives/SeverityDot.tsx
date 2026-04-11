import React from 'react';
import styles from './SeverityDot.module.css';

type Severity = 'critical' | 'high' | 'medium' | 'low';

interface SeverityDotProps {
  severity: Severity;
  className?: string;
  style?: React.CSSProperties;
}

export function SeverityDot({ severity, className, style }: SeverityDotProps) {
  const label = `Severity: ${severity.charAt(0).toUpperCase()}${severity.slice(1)}`;
  return (
    <span
      className={[styles.dot, styles[severity], className].filter(Boolean).join(' ')}
      style={style}
      role="img"
      aria-label={label}
    />
  );
}
