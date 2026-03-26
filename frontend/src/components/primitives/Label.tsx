import styles from './Label.module.css';

type LabelVariant = 'danger' | 'attention' | 'success' | 'done' | 'muted' | 'accent' | 'severe';

interface LabelProps {
  variant?: LabelVariant;
  children: React.ReactNode;
  className?: string;
}

export function Label({ variant = 'muted', children, className }: LabelProps) {
  const cls = [styles.label, styles[variant], className].filter(Boolean).join(' ');
  return <span className={cls}>{children}</span>;
}
