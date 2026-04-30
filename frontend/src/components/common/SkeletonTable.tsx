import styles from './Skeleton.module.css';

interface SkeletonTableProps {
  /** Number of columns. Default 4. */
  columns?: number;
  /** Number of data rows (excluding header). Default 5. */
  rows?: number;
  className?: string;
}

/**
 * Animated skeleton placeholder that mimics a DataTable layout.
 *
 * Respects `prefers-reduced-motion` by disabling animation.
 */
export function SkeletonTable({ columns = 4, rows = 5, className }: SkeletonTableProps) {
  return (
    <div
      className={[styles.tableWrap, className].filter(Boolean).join(' ')}
      aria-hidden="true"
      role="presentation"
    >
      <div className={styles.tableRow}>
        {Array.from({ length: columns }, (_, i) => (
          <div key={`h-${i}`} className={`${styles.skeleton} ${styles.tableCell}`} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={`r-${r}`} className={styles.tableRow}>
          {Array.from({ length: columns }, (_, c) => (
            <div key={`c-${c}`} className={`${styles.skeleton} ${styles.tableCell}`} />
          ))}
        </div>
      ))}
    </div>
  );
}
