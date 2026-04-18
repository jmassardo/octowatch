import styles from './Label.module.css';

type LabelVariant = 'danger' | 'attention' | 'success' | 'done' | 'muted' | 'accent' | 'severe';

const VARIANT_LABELS: Record<LabelVariant, string> = {
  danger: 'Danger',
  attention: 'Warning',
  success: 'Success',
  done: 'Done',
  muted: '',
  accent: 'Info',
  severe: 'Severe',
};

interface LabelProps {
  variant?: LabelVariant;
  children: React.ReactNode;
  className?: string;
  title?: string;
}

export function Label({ variant = 'muted', children, className, title }: LabelProps) {
  const cls = [styles.label, styles[variant], className].filter(Boolean).join(' ');
  const statusPrefix = VARIANT_LABELS[variant];
  return (
    <span className={cls} title={title}>
      {statusPrefix && <span className="sr-only">{statusPrefix}: </span>}
      {children}
    </span>
  );
}
