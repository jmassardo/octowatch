import styles from './SampleDataBanner.module.css';

interface SampleDataBannerProps {
  message?: string;
}

export function SampleDataBanner({ message }: SampleDataBannerProps) {
  return (
    <div className={styles.banner} role="status">
      <span className={styles.icon}>ℹ️</span>
      <span>
        {message ??
          'This page displays sample data for demonstration purposes. Connect your GitHub audit log source to see real data.'}
      </span>
    </div>
  );
}
