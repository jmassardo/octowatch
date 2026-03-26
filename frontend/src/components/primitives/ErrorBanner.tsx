import styles from './ErrorBanner.module.css';
import { Button } from './Button';

interface ErrorBannerProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message = 'Something went wrong', onRetry }: ErrorBannerProps) {
  return (
    <div className={styles.banner}>
      <span>{message}</span>
      {onRetry && (
        <Button size="sm" onClick={onRetry} className={styles.retry}>
          Retry
        </Button>
      )}
    </div>
  );
}
