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
  onClick?: (e: React.MouseEvent) => void;
}

export function Label({ variant = 'muted', children, className, title, onClick }: LabelProps) {
  const cls = [styles.label, styles[variant], onClick && styles.clickable, className]
    .filter(Boolean)
    .join(' ');
  const statusPrefix = VARIANT_LABELS[variant];
  return (
    <span
      className={cls}
      title={title}
      onClick={
        onClick
          ? (e) => {
              e.stopPropagation();
              onClick(e);
            }
          : undefined
      }
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                onClick(e as unknown as React.MouseEvent);
              }
            }
          : undefined
      }
    >
      {statusPrefix && <span className="sr-only">{statusPrefix}: </span>}
      {children}
    </span>
  );
}
