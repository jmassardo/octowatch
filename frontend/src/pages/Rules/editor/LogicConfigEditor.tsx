import { useCallback, useMemo } from 'react';
import type { ChangeEvent } from 'react';
import type { LogicConfig, FieldCondition, SequenceStep, XConfig } from './types';
import { ActionFilters } from './ActionFilters';
import { FieldConditions } from './FieldConditions';
import { SequenceSteps } from './SequenceSteps';
import styles from './LogicConfigEditor.module.css';

type LogicType = 'pattern' | 'threshold' | 'sequence' | 'statistical';

interface LogicConfigEditorProps {
  logicType: LogicType;
  config: LogicConfig;
  onChange: (config: LogicConfig) => void;
  errors?: string[];
}

const AGGREGATION_KEYS = [
  { value: 'actor', label: 'Actor' },
  { value: 'repo', label: 'Repository' },
  { value: 'org', label: 'Organization' },
] as const;

const DISTINCT_COUNT_FIELDS = [
  { value: '', label: '(none)' },
  { value: 'actor', label: 'actor' },
  { value: 'org', label: 'org' },
  { value: 'repo', label: 'repo' },
  { value: 'source_ip', label: 'source_ip' },
  { value: 'user_agent', label: 'user_agent' },
  { value: 'geo_country_code', label: 'geo_country_code' },
  { value: 'action', label: 'action' },
] as const;

function getDefaults(logicType: LogicType): LogicConfig {
  const base: LogicConfig = {
    action_filters: [],
    field_conditions: [],
    confidence: 0.5,
  };

  switch (logicType) {
    case 'threshold':
      return {
        ...base,
        threshold: 10,
        time_window_minutes: 60,
        aggregation_key: 'actor',
      };
    case 'sequence':
      return {
        ...base,
        sequence_steps: [
          { action: '', min_count: 1 },
          { action: '', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
      };
    case 'statistical':
      return {
        ...base,
        time_window_minutes: 60,
        x_config: {
          engine: 'impossible_travel',
          distance_threshold_km: 500,
          speed_threshold_kmh: 900,
          suppress_proxy_ips: true,
        },
      };
    case 'pattern':
    default:
      return base;
  }
}

function resolveConfig(logicType: LogicType, config: LogicConfig): LogicConfig {
  const isEmpty =
    Object.keys(config).length === 0 ||
    (config.action_filters === undefined &&
      config.field_conditions === undefined &&
      config.confidence === undefined &&
      config.threshold === undefined &&
      config.time_window_minutes === undefined &&
      config.sequence_steps === undefined &&
      config.x_config === undefined);

  if (isEmpty) {
    return getDefaults(logicType);
  }
  return config;
}

export function LogicConfigEditor({
  logicType,
  config: rawConfig,
  onChange,
  errors,
}: LogicConfigEditorProps) {
  const config = useMemo(
    () => resolveConfig(logicType, rawConfig),
    [logicType, rawConfig],
  );

  const update = useCallback(
    (patch: Partial<LogicConfig>) => {
      onChange({ ...config, ...patch });
    },
    [config, onChange],
  );

  const handleActionFiltersChange = useCallback(
    (actions: string[]) => update({ action_filters: actions }),
    [update],
  );

  const handleFieldConditionsChange = useCallback(
    (conditions: FieldCondition[]) => update({ field_conditions: conditions }),
    [update],
  );

  const handleConfidenceChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      update({ confidence: parseFloat(e.target.value) });
    },
    [update],
  );

  const handleThresholdChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const parsed = parseInt(e.target.value, 10);
      update({ threshold: Number.isNaN(parsed) ? 1 : Math.max(1, parsed) });
    },
    [update],
  );

  const handleTimeWindowChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const parsed = parseInt(e.target.value, 10);
      update({ time_window_minutes: Number.isNaN(parsed) ? 1 : Math.max(1, parsed) });
    },
    [update],
  );

  const handleAggregationKeyChange = useCallback(
    (e: ChangeEvent<HTMLSelectElement>) => {
      update({ aggregation_key: e.target.value });
    },
    [update],
  );

  const handleDistinctCountFieldChange = useCallback(
    (e: ChangeEvent<HTMLSelectElement>) => {
      const val = e.target.value;
      update({ distinct_count_field: val || undefined });
    },
    [update],
  );

  const handleSequenceStepsChange = useCallback(
    (steps: SequenceStep[]) => update({ sequence_steps: steps }),
    [update],
  );

  const handleXConfigChange = useCallback(
    (patch: Partial<XConfig>) => {
      const current = config.x_config ?? {
        engine: 'impossible_travel',
        distance_threshold_km: 500,
        speed_threshold_kmh: 900,
        suppress_proxy_ips: true,
      };
      update({ x_config: { ...current, ...patch } });
    },
    [config.x_config, update],
  );

  const confidenceValue = config.confidence ?? 0.5;

  return (
    <div className={styles.editor} role="form" aria-label="Logic configuration editor">
      {errors && errors.length > 0 && (
        <ul className={styles.errorList} role="alert">
          {errors.map((err, i) => (
            <li key={i} className={styles.errorItem}>
              {err}
            </li>
          ))}
        </ul>
      )}

      {/* Common: Action Filters */}
      <section className={styles.section}>
        <h3 className={styles.sectionHeader}>Action Filters</h3>
        <ActionFilters
          actions={config.action_filters ?? []}
          onChange={handleActionFiltersChange}
        />
      </section>

      {/* Common: Field Conditions */}
      <section className={styles.section}>
        <h3 className={styles.sectionHeader}>Field Conditions</h3>
        <FieldConditions
          conditions={config.field_conditions ?? []}
          onChange={handleFieldConditionsChange}
        />
      </section>

      {/* Common: Confidence */}
      <section className={styles.section}>
        <h3 className={styles.sectionHeader}>Confidence</h3>
        <div className={styles.sliderRow}>
          <input
            type="range"
            className={styles.slider}
            min={0}
            max={1}
            step={0.05}
            value={confidenceValue}
            onChange={handleConfidenceChange}
            aria-label="Confidence score"
          />
          <span className={styles.sliderValue}>{confidenceValue.toFixed(2)}</span>
        </div>
      </section>

      {/* Threshold-specific */}
      {logicType === 'threshold' && (
        <ThresholdSection
          threshold={config.threshold}
          timeWindowMinutes={config.time_window_minutes}
          aggregationKey={config.aggregation_key}
          distinctCountField={config.distinct_count_field}
          onThresholdChange={handleThresholdChange}
          onTimeWindowChange={handleTimeWindowChange}
          onAggregationKeyChange={handleAggregationKeyChange}
          onDistinctCountFieldChange={handleDistinctCountFieldChange}
        />
      )}

      {/* Sequence-specific */}
      {logicType === 'sequence' && (
        <SequenceSection
          steps={config.sequence_steps ?? []}
          aggregationKey={config.aggregation_key}
          timeWindowMinutes={config.time_window_minutes}
          onStepsChange={handleSequenceStepsChange}
          onAggregationKeyChange={handleAggregationKeyChange}
          onTimeWindowChange={handleTimeWindowChange}
        />
      )}

      {/* Statistical-specific */}
      {logicType === 'statistical' && (
        <StatisticalSection
          xConfig={config.x_config}
          timeWindowMinutes={config.time_window_minutes}
          onXConfigChange={handleXConfigChange}
          onTimeWindowChange={handleTimeWindowChange}
        />
      )}
    </div>
  );
}

/* ─── Threshold Section ─────────────────────────────────────────────── */

interface ThresholdSectionProps {
  threshold?: number;
  timeWindowMinutes?: number;
  aggregationKey?: string;
  distinctCountField?: string;
  onThresholdChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onTimeWindowChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onAggregationKeyChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  onDistinctCountFieldChange: (e: ChangeEvent<HTMLSelectElement>) => void;
}

function ThresholdSection({
  threshold,
  timeWindowMinutes,
  aggregationKey,
  distinctCountField,
  onThresholdChange,
  onTimeWindowChange,
  onAggregationKeyChange,
  onDistinctCountFieldChange,
}: ThresholdSectionProps) {
  return (
    <section className={styles.section}>
      <h3 className={styles.sectionHeader}>Threshold</h3>
      <div className={styles.fieldGrid}>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="threshold-count">
            Alert when count exceeds
          </label>
          <input
            id="threshold-count"
            type="number"
            className={styles.fieldInput}
            value={threshold ?? 10}
            onChange={onThresholdChange}
            min={1}
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="threshold-window">
            Within time window (minutes)
          </label>
          <input
            id="threshold-window"
            type="number"
            className={styles.fieldInput}
            value={timeWindowMinutes ?? 60}
            onChange={onTimeWindowChange}
            min={1}
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="threshold-agg-key">
            Group events by
          </label>
          <select
            id="threshold-agg-key"
            className={styles.fieldSelect}
            value={aggregationKey ?? 'actor'}
            onChange={onAggregationKeyChange}
          >
            {AGGREGATION_KEYS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="threshold-distinct">
            Count distinct values of
          </label>
          <select
            id="threshold-distinct"
            className={styles.fieldSelect}
            value={distinctCountField ?? ''}
            onChange={onDistinctCountFieldChange}
          >
            {DISTINCT_COUNT_FIELDS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </section>
  );
}

/* ─── Sequence Section ──────────────────────────────────────────────── */

interface SequenceSectionProps {
  steps: SequenceStep[];
  aggregationKey?: string;
  timeWindowMinutes?: number;
  onStepsChange: (steps: SequenceStep[]) => void;
  onAggregationKeyChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  onTimeWindowChange: (e: ChangeEvent<HTMLInputElement>) => void;
}

function SequenceSection({
  steps,
  aggregationKey,
  timeWindowMinutes,
  onStepsChange,
  onAggregationKeyChange,
  onTimeWindowChange,
}: SequenceSectionProps) {
  return (
    <section className={styles.section}>
      <h3 className={styles.sectionHeader}>Sequence Steps</h3>
      <SequenceSteps steps={steps} onChange={onStepsChange} />
      <div className={styles.fieldGrid}>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="sequence-agg-key">
            Group events by
          </label>
          <select
            id="sequence-agg-key"
            className={styles.fieldSelect}
            value={aggregationKey ?? 'actor'}
            onChange={onAggregationKeyChange}
          >
            {AGGREGATION_KEYS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="sequence-window">
            Within time window (minutes)
          </label>
          <input
            id="sequence-window"
            type="number"
            className={styles.fieldInput}
            value={timeWindowMinutes ?? 60}
            onChange={onTimeWindowChange}
            min={1}
          />
        </div>
      </div>
    </section>
  );
}

/* ─── Statistical Section ───────────────────────────────────────────── */

interface StatisticalSectionProps {
  xConfig?: XConfig;
  timeWindowMinutes?: number;
  onXConfigChange: (patch: Partial<XConfig>) => void;
  onTimeWindowChange: (e: ChangeEvent<HTMLInputElement>) => void;
}

function StatisticalSection({
  xConfig,
  timeWindowMinutes,
  onXConfigChange,
  onTimeWindowChange,
}: StatisticalSectionProps) {
  const cfg = xConfig ?? {
    engine: 'impossible_travel',
    distance_threshold_km: 500,
    speed_threshold_kmh: 900,
    suppress_proxy_ips: true,
  };

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionHeader}>Statistical Analysis</h3>
      <div className={styles.fieldGrid}>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="stat-engine">
            Engine
          </label>
          <select
            id="stat-engine"
            className={styles.fieldSelect}
            value={cfg.engine}
            onChange={(e) => onXConfigChange({ engine: e.target.value })}
          >
            <option value="impossible_travel">impossible_travel</option>
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="stat-distance">
            Distance threshold (km)
          </label>
          <input
            id="stat-distance"
            type="number"
            className={styles.fieldInput}
            value={cfg.distance_threshold_km ?? 500}
            onChange={(e) => {
              const parsed = parseInt(e.target.value, 10);
              onXConfigChange({
                distance_threshold_km: Number.isNaN(parsed) ? 500 : parsed,
              });
            }}
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="stat-speed">
            Speed threshold (km/h)
          </label>
          <input
            id="stat-speed"
            type="number"
            className={styles.fieldInput}
            value={cfg.speed_threshold_kmh ?? 900}
            onChange={(e) => {
              const parsed = parseInt(e.target.value, 10);
              onXConfigChange({
                speed_threshold_kmh: Number.isNaN(parsed) ? 900 : parsed,
              });
            }}
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="stat-window">
            Time window (minutes)
          </label>
          <input
            id="stat-window"
            type="number"
            className={styles.fieldInput}
            value={timeWindowMinutes ?? 60}
            onChange={onTimeWindowChange}
            min={1}
          />
        </div>
        <div className={styles.fieldGroupCheck}>
          <label className={styles.checkLabel} htmlFor="stat-suppress-proxy">
            <input
              id="stat-suppress-proxy"
              type="checkbox"
              checked={cfg.suppress_proxy_ips ?? true}
              onChange={(e) =>
                onXConfigChange({ suppress_proxy_ips: e.target.checked })
              }
            />
            Suppress proxy IPs
          </label>
        </div>
      </div>
    </section>
  );
}
