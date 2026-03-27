import styles from './SampleDataBanner.module.css';

export function SampleDataBanner() {
  return (
    <div className={styles.banner} role="status">
      <span className={styles.icon}>ℹ️</span>
      <span>
        This page displays sample data for demonstration purposes. Connect your GitHub audit log
        source to see real data.
      </span>
    </div>
  );
}
