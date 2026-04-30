import styles from './Toast.module.css';

export type ToastVariant = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  message: string;
  variant: ToastVariant;
  duration: number;
}

interface ToastProps {
  item: ToastItem;
  onDismiss: (id: string) => void;
}

const VARIANT_ICONS: Record<ToastVariant, string> = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
};

/**
 * A single toast notification with dismiss support.
 *
 * Uses `role="alert"` and `aria-live="assertive"` so screen readers
 * announce the message immediately.
 */
export function Toast({ item, onDismiss }: ToastProps) {
  return (
    <div
      className={`${styles.toast} ${styles[item.variant]}`}
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <span className={styles.icon} aria-hidden="true">
        {VARIANT_ICONS[item.variant]}
      </span>
      <span className={styles.body}>{item.message}</span>
      <button
        className={styles.dismiss}
        onClick={() => onDismiss(item.id)}
        aria-label="Dismiss notification"
      >
        ✕
      </button>
    </div>
  );
}
