import { useState } from 'react';
import { Drawer } from '../primitives/Drawer';
import { Button } from '../primitives/Button';
import { STAT_PILL_CATEGORIES, STAT_PILL_REGISTRY, getMetricsByCategory } from './statPillRegistry';
import { getDefaultStatPillConfig, type StatPillConfig } from './statPillConfigStorage';
import styles from './StatPillConfig.module.css';

interface StatPillConfigProps {
  open: boolean;
  onClose: () => void;
  config: StatPillConfig;
  onSave: (config: StatPillConfig) => void;
}

export function StatPillConfigDrawer({ open, onClose, config, onSave }: StatPillConfigProps) {
  const [draft, setDraft] = useState<StatPillConfig>(config);

  function handleToggle(metricId: string) {
    setDraft((current) => ({
      ...current,
      enabledPills: current.enabledPills.includes(metricId)
        ? current.enabledPills.filter((id) => id !== metricId)
        : [...current.enabledPills, metricId],
    }));
  }

  function moveMetric(metricId: string, direction: -1 | 1) {
    setDraft((current) => {
      const index = current.order.indexOf(metricId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.order.length) return current;
      const order = [...current.order];
      [order[index], order[nextIndex]] = [order[nextIndex]!, order[index]!];
      return { ...current, order };
    });
  }

  function updateThreshold(metricId: string, field: 'warning' | 'critical', rawValue: string) {
    const value = Number(rawValue);
    setDraft((current) => ({
      ...current,
      thresholds: {
        ...current.thresholds,
        [metricId]: {
          ...(current.thresholds[metricId] ?? STAT_PILL_REGISTRY[metricId]!.defaultThresholds),
          [field]: Number.isFinite(value) ? value : 0,
        },
      },
    }));
  }

  return (
    <Drawer open={open} onClose={onClose} title="Configure stat pills">
      <div className={styles.content}>
        <p className={styles.description}>
          Choose which metrics appear on the Operations dashboard, reorder them, and tune warning
          and critical thresholds.
        </p>

        {STAT_PILL_CATEGORIES.map((category) => (
          <section key={category.id} className={styles.section}>
            <h3 className={styles.sectionTitle}>{category.label}</h3>
            <div className={styles.metricList}>
              {getMetricsByCategory(category.id).map((metric) => {
                const enabled = draft.enabledPills.includes(metric.id);
                const orderIndex = draft.order.indexOf(metric.id);
                const thresholds = draft.thresholds[metric.id] ?? metric.defaultThresholds;

                return (
                  <div key={metric.id} className={styles.metricCard}>
                    <div className={styles.metricHeader}>
                      <label className={styles.metricToggle}>
                        <input
                          type="checkbox"
                          checked={enabled}
                          onChange={() => handleToggle(metric.id)}
                        />
                        <span className={styles.metricIcon}>{metric.icon}</span>
                        <span>{metric.label}</span>
                      </label>
                      <div className={styles.orderControls}>
                        <button
                          type="button"
                          className={styles.orderButton}
                          onClick={() => moveMetric(metric.id, -1)}
                          disabled={orderIndex <= 0}
                          aria-label={`Move ${metric.label} up`}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className={styles.orderButton}
                          onClick={() => moveMetric(metric.id, 1)}
                          disabled={orderIndex < 0 || orderIndex >= draft.order.length - 1}
                          aria-label={`Move ${metric.label} down`}
                        >
                          ↓
                        </button>
                      </div>
                    </div>

                    <div className={styles.thresholdGrid}>
                      <label className={styles.thresholdField}>
                        <span>Warning</span>
                        <div className={styles.inputWrap}>
                          <input
                            type="number"
                            step="0.1"
                            value={thresholds.warning}
                            onChange={(event) =>
                              updateThreshold(metric.id, 'warning', event.target.value)
                            }
                            aria-label={`${metric.label} warning threshold`}
                          />
                          {metric.thresholdUnitLabel && (
                            <span className={styles.unit}>{metric.thresholdUnitLabel}</span>
                          )}
                        </div>
                      </label>
                      <label className={styles.thresholdField}>
                        <span>Critical</span>
                        <div className={styles.inputWrap}>
                          <input
                            type="number"
                            step="0.1"
                            value={thresholds.critical}
                            onChange={(event) =>
                              updateThreshold(metric.id, 'critical', event.target.value)
                            }
                            aria-label={`${metric.label} critical threshold`}
                          />
                          {metric.thresholdUnitLabel && (
                            <span className={styles.unit}>{metric.thresholdUnitLabel}</span>
                          )}
                        </div>
                      </label>
                    </div>
                    <div className={styles.metricMeta}>
                      {enabled ? `Visible · position ${orderIndex + 1}` : 'Hidden'}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))}

        <div className={styles.actions}>
          <Button type="button" onClick={() => setDraft(getDefaultStatPillConfig())}>
            Reset to defaults
          </Button>
          <div className={styles.actionGroup}>
            <Button type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="button" variant="primary" onClick={() => onSave(draft)}>
              Save
            </Button>
          </div>
        </div>
      </div>
    </Drawer>
  );
}
