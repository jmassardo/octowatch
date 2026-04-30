import { Button } from '../primitives/Button';
import styles from './EmptyState.module.css';

type EmptyStateVariant = 'default' | 'filtered' | 'setup';

interface EmptyStateProps {
  /** Emoji or icon string displayed above the title. */
  icon?: string;
  /** Main heading. */
  title: string;
  /** Descriptive text below the heading. */
  description?: string;
  /** Label for the call-to-action button. */
  ctaLabel?: string;
  /** Callback fired when the CTA button is clicked. */
  ctaAction?: () => void;
  /** Pre-built variant that sets sensible defaults. */
  variant?: EmptyStateVariant;
}

const VARIANT_DEFAULTS: Record<EmptyStateVariant, Partial<EmptyStateProps>> = {
  default: {
    icon: '📭',
    title: 'No data yet',
    description: 'Get started by configuring your data source.',
    ctaLabel: 'Go to setup',
  },
  filtered: {
    icon: '🔍',
    title: 'No results match filters',
    description: 'Try adjusting your search criteria or clearing filters.',
    ctaLabel: 'Clear filters',
  },
  setup: {
    icon: '🛡️',
    title: 'No detections found',
    description: 'No detections match the current filters. Try resetting them.',
    ctaLabel: 'Reset filters',
  },
};

/**
 * EmptyState — a consistent placeholder shown when a list or table has no data.
 *
 * Supports three pre-built variants (`default`, `filtered`, `setup`) with
 * sensible defaults that can be overridden via props.
 */
export function EmptyState(props: EmptyStateProps) {
  const variant = props.variant ?? 'default';
  const defaults = VARIANT_DEFAULTS[variant];

  const icon = props.icon ?? defaults.icon;
  const title = props.title ?? defaults.title;
  const description = props.description ?? defaults.description;
  const ctaLabel = props.ctaLabel ?? defaults.ctaLabel;
  const ctaAction = props.ctaAction;

  return (
    <div className={styles.wrapper} role="status">
      {icon && (
        <span className={styles.icon} aria-hidden="true">
          {icon}
        </span>
      )}
      <h3 className={styles.title}>{title}</h3>
      {description && <p className={styles.description}>{description}</p>}
      {ctaLabel && ctaAction && (
        <div className={styles.cta}>
          <Button variant="primary" size="sm" onClick={ctaAction}>
            {ctaLabel}
          </Button>
        </div>
      )}
    </div>
  );
}
