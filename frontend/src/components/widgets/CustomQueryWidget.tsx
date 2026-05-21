/**
 * CustomQueryWidget — the placeholder/overview component shown in the widget
 * catalog and customize picker. When a user has no custom widgets yet it shows
 * a prompt; otherwise it shows a count and link to create more.
 *
 * The actual per-instance rendering is handled by customQueryWidgetFactory.tsx.
 */

import { useCallback, useMemo } from 'react';
import { loadCustomWidgetConfigs } from './customWidgetConfigStorage';
import styles from './Widgets.module.css';

export function CustomQueryWidget() {
  const configs = useMemo(() => loadCustomWidgetConfigs(), []);

  const handleCreate = useCallback(() => {
    window.dispatchEvent(new CustomEvent('octowatch:open-custom-widget-dialog'));
  }, []);

  if (configs.length === 0) {
    return (
      <div className={styles.metricRow}>
        <div>
          <div className={styles.metricLabel}>
            Create custom widgets from your saved queries to visualize data your way.
          </div>
          <button type="button" className={styles.actionLink} onClick={handleCreate}>
            Create custom widget
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className={styles.metricRow}>
        <div>
          <div className={styles.metricValue}>{configs.length}</div>
          <div className={styles.metricLabel}>custom widget{configs.length !== 1 ? 's' : ''}</div>
        </div>
        <button type="button" className={styles.actionLink} onClick={handleCreate}>
          Create another
        </button>
      </div>
    </div>
  );
}
