import { Button } from '../primitives/Button';
import { Spinner } from '../primitives/Spinner';
import styles from './LoadingButton.module.css';

interface LoadingButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Whether an async action is in progress. */
  loading?: boolean;
  variant?: 'default' | 'primary' | 'danger';
  size?: 'sm' | 'md';
}

/**
 * A button that shows an inline spinner while `loading` is true and
 * disables itself to prevent duplicate submissions.
 */
export function LoadingButton({
  loading = false,
  children,
  disabled,
  className,
  ...rest
}: LoadingButtonProps) {
  return (
    <Button
      className={[styles.btn, className].filter(Boolean).join(' ')}
      disabled={disabled || loading}
      aria-busy={loading}
      {...rest}
    >
      {loading ? (
        <span className={styles.spinnerWrap}>
          <Spinner size={14} />
          {children}
        </span>
      ) : (
        children
      )}
    </Button>
  );
}
