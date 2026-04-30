import { Button } from '../primitives/Button';
import styles from './ErrorState.module.css';

interface ErrorStateProps {
  /** Emoji or icon displayed above the title. */
  icon?: string;
  /** Heading text. */
  title?: string;
  /** Human-friendly error message (no raw API errors). */
  message?: string;
  /** Callback for the retry button. Always rendered when provided. */
  onRetry?: () => void;
}

/**
 * ErrorState — a user-friendly error placeholder for failed data loads.
 *
 * Always shows a "Retry" button when `onRetry` is provided. Includes a
 * pre-built network-error variant via default props.
 */
export function ErrorState({
  icon = '⚠️',
  title = 'Something went wrong',
  message = 'Unable to connect — check your network and try again.',
  onRetry,
}: ErrorStateProps) {
  return (
    <div className={styles.wrapper} role="alert">
      <span className={styles.icon} aria-hidden="true">
        {icon}
      </span>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.message}>{message}</p>
      {onRetry && (
        <div className={styles.actions}>
          <Button variant="primary" size="sm" onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}
