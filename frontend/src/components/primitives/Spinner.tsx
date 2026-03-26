import styles from './Spinner.module.css';

interface SpinnerProps {
  size?: number;
  className?: string;
}

export function Spinner({ size = 20, className }: SpinnerProps) {
  return (
    <div
      className={[styles.spinner, className].filter(Boolean).join(' ')}
      style={{ width: size, height: size }}
    />
  );
}
