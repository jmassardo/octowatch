import React from 'react';
import styles from './SeverityDot.module.css';

type Severity = 'critical' | 'high' | 'medium' | 'low';

interface SeverityDotProps {
  severity: Severity;
  className?: string;
  style?: React.CSSProperties;
}

export function SeverityDot({ severity, className, style }: SeverityDotProps) {
  return <span className={[styles.dot, styles[severity], className].filter(Boolean).join(' ')} style={style} />;
}
