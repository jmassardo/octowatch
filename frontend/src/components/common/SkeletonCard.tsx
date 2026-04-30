import styles from './Skeleton.module.css';

interface SkeletonCardProps {
  /** Number of text lines to render. Default 3. */
  lines?: number;
  className?: string;
}

/**
 * Animated skeleton placeholder that mimics a Card layout.
 *
 * Respects `prefers-reduced-motion` by disabling animation.
 */
export function SkeletonCard({ lines = 3, className }: SkeletonCardProps) {
  return (
    <div
      className={[styles.cardWrap, className].filter(Boolean).join(' ')}
      aria-hidden="true"
      role="presentation"
    >
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className={`${styles.skeleton} ${i === lines - 1 ? styles.cardLineShort : styles.cardLineLong}`}
        />
      ))}
    </div>
  );
}
