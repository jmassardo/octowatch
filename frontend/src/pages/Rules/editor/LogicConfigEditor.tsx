import { useCallback, useMemo } from 'react';
import type { ChangeEvent } from 'react';
import type { LogicConfig, FieldCondition, SequenceStep, XConfig } from './types';
import { ActionFilters } from './ActionFilters';
import { FieldConditions } from './FieldConditions';
import { SequenceSteps } from './SequenceSteps';
import styles from './LogicConfigEditor.module.css';

type LogicType = 'pattern' | 'threshold' | 'sequence' | 'statistical' | 'posture';

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
    case 'posture':
      return {
        ...base,
        action_filters: undefined,
        field_conditions: undefined,
        entity_type: 'org',
        check_type: 'field_value',
        field: '',
        operator: 'eq',
        expected: '',
        value: '',
      };
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
      config.x_config === undefined &&
      (config as Record<string, unknown>).entity_type === undefined);

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
  const config = useMemo(() => resolveConfig(logicType, rawConfig), [logicType, rawConfig]);

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

      {/* Common: Action Filters (not used by posture rules) */}
      {logicType !== 'posture' && (
        <section className={styles.section}>
          <h3 className={styles.sectionHeader}>Action Filters</h3>
          <ActionFilters
            actions={config.action_filters ?? []}
            onChange={handleActionFiltersChange}
          />
        </section>
      )}

      {/* Common: Field Conditions (not used by posture rules) */}
      {logicType !== 'posture' && (
        <section className={styles.section}>
          <h3 className={styles.sectionHeader}>Field Conditions</h3>
          <FieldConditions
            conditions={config.field_conditions ?? []}
            onChange={handleFieldConditionsChange}
          />
        </section>
      )}

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

      {/* Posture-specific */}
      {logicType === 'posture' && <PostureSection config={config} onChange={update} />}
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
              onChange={(e) => onXConfigChange({ suppress_proxy_ips: e.target.checked })}
            />
            Suppress proxy IPs
          </label>
        </div>
      </div>
    </section>
  );
}

/* ─── Posture Section ───────────────────────────────────────────────── */

const POSTURE_ENTITY_TYPES = [
  { value: 'org', label: 'Organization' },
  { value: 'repo', label: 'Repository' },
  { value: 'branch_protection', label: 'Branch Protection' },
] as const;

const POSTURE_CHECK_TYPES = [
  { value: 'field_value', label: 'Field Value Check' },
  { value: 'missing_protection', label: 'Missing Protection' },
] as const;

const POSTURE_OPERATORS = [
  { value: 'eq', label: 'equals' },
  { value: 'ne', label: 'not equals' },
  { value: 'lt', label: 'less than' },
  { value: 'lte', label: 'less or equal' },
  { value: 'gt', label: 'greater than' },
  { value: 'gte', label: 'greater or equal' },
  { value: 'in', label: 'in (list)' },
  { value: 'not_in', label: 'not in (list)' },
] as const;

const ORG_FIELDS = [
  { value: 'two_factor_required', label: 'Two-factor required' },
  { value: 'default_repo_permission', label: 'Default repo permission' },
  { value: 'members_can_fork_private_repos', label: 'Members can fork private repos' },
  { value: 'members_can_create_public_repos', label: 'Members can create public repos' },
  { value: 'ip_allow_list_enabled', label: 'IP allow list enabled' },
  { value: 'ip_allow_list_for_installed_apps_enabled', label: 'IP allow list for apps enabled' },
  { value: 'visibility', label: 'Visibility' },
];

const REPO_FIELDS = [
  { value: 'visibility', label: 'Visibility' },
  { value: 'archived', label: 'Archived' },
  { value: 'fork', label: 'Fork' },
  { value: 'default_branch', label: 'Default branch' },
];

const BRANCH_PROTECTION_FIELDS = [
  { value: 'required_reviews', label: 'Required reviews' },
  { value: 'enforce_admins', label: 'Enforce admins' },
];

function getFieldsForEntityType(entityType: string) {
  switch (entityType) {
    case 'org':
      return ORG_FIELDS;
    case 'repo':
      return REPO_FIELDS;
    case 'branch_protection':
      return BRANCH_PROTECTION_FIELDS;
    default:
      return [];
  }
}

interface PostureSectionProps {
  config: LogicConfig;
  onChange: (patch: Partial<LogicConfig>) => void;
}

function PostureSection({ config, onChange }: PostureSectionProps) {
  const entityType = ((config as Record<string, unknown>).entity_type as string) ?? 'org';
  const checkType = ((config as Record<string, unknown>).check_type as string) ?? 'field_value';
  const field = ((config as Record<string, unknown>).field as string) ?? '';
  const operator = ((config as Record<string, unknown>).operator as string) ?? 'eq';
  const expected = (config as Record<string, unknown>).expected;
  const value = (config as Record<string, unknown>).value;
  const scope = ((config as Record<string, unknown>).scope as Record<string, unknown>) ?? {};

  const availableFields = getFieldsForEntityType(entityType);
  const isMissingProtection = checkType === 'missing_protection';
  const useExpected = expected !== undefined;

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionHeader}>Posture Check</h3>
      <p className={styles.sectionHint}>
        Evaluates the current state of synced metadata — not audit log events.
      </p>
      <div className={styles.fieldGrid}>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="posture-entity-type">
            Entity type
          </label>
          <select
            id="posture-entity-type"
            className={styles.fieldSelect}
            value={entityType}
            onChange={(e) =>
              onChange({
                ...config,
                entity_type: e.target.value,
                field: '',
              } as unknown as Partial<LogicConfig>)
            }
          >
            {POSTURE_ENTITY_TYPES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="posture-check-type">
            Check type
          </label>
          <select
            id="posture-check-type"
            className={styles.fieldSelect}
            value={checkType}
            onChange={(e) =>
              onChange({ ...config, check_type: e.target.value } as unknown as Partial<LogicConfig>)
            }
          >
            {POSTURE_CHECK_TYPES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {!isMissingProtection && (
          <>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel} htmlFor="posture-field">
                Field to check
              </label>
              <select
                id="posture-field"
                className={styles.fieldSelect}
                value={field}
                onChange={(e) =>
                  onChange({ ...config, field: e.target.value } as unknown as Partial<LogicConfig>)
                }
              >
                <option value="">Select a field...</option>
                {availableFields.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel} htmlFor="posture-mode">
                Comparison mode
              </label>
              <select
                id="posture-mode"
                className={styles.fieldSelect}
                value={useExpected ? 'expected' : 'operator'}
                onChange={(e) => {
                  if (e.target.value === 'expected') {
                    onChange({
                      ...config,
                      expected: true,
                      operator: undefined,
                      value: undefined,
                    } as unknown as Partial<LogicConfig>);
                  } else {
                    onChange({
                      ...config,
                      expected: undefined,
                      operator: 'eq',
                      value: '',
                    } as unknown as Partial<LogicConfig>);
                  }
                }}
              >
                <option value="expected">Alert when NOT equal to expected value</option>
                <option value="operator">Custom operator comparison</option>
              </select>
            </div>

            {useExpected ? (
              <div className={styles.fieldGroup}>
                <label className={styles.fieldLabel} htmlFor="posture-expected">
                  Expected value (alert fires when actual ≠ expected)
                </label>
                <input
                  id="posture-expected"
                  type="text"
                  className={styles.fieldInput}
                  value={String(expected ?? '')}
                  onChange={(e) => {
                    let parsed: unknown = e.target.value;
                    if (parsed === 'true') parsed = true;
                    else if (parsed === 'false') parsed = false;
                    else if (!isNaN(Number(parsed)) && parsed !== '') parsed = Number(parsed);
                    onChange({ ...config, expected: parsed } as unknown as Partial<LogicConfig>);
                  }}
                  placeholder="e.g., true, false, read"
                />
              </div>
            ) : (
              <>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel} htmlFor="posture-operator">
                    Operator
                  </label>
                  <select
                    id="posture-operator"
                    className={styles.fieldSelect}
                    value={operator}
                    onChange={(e) =>
                      onChange({
                        ...config,
                        operator: e.target.value,
                      } as unknown as Partial<LogicConfig>)
                    }
                  >
                    {POSTURE_OPERATORS.map((op) => (
                      <option key={op.value} value={op.value}>
                        {op.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel} htmlFor="posture-value">
                    Value
                  </label>
                  <input
                    id="posture-value"
                    type="text"
                    className={styles.fieldInput}
                    value={String(value ?? '')}
                    onChange={(e) => {
                      let parsed: unknown = e.target.value;
                      if (parsed === 'true') parsed = true;
                      else if (parsed === 'false') parsed = false;
                      else if (!isNaN(Number(parsed)) && parsed !== '') parsed = Number(parsed);
                      onChange({ ...config, value: parsed } as unknown as Partial<LogicConfig>);
                    }}
                    placeholder="e.g., true, write, 1"
                  />
                </div>
              </>
            )}
          </>
        )}

        <div className={styles.fieldGroup}>
          <label className={styles.fieldLabel} htmlFor="posture-scope">
            Scope filter (JSON, optional)
          </label>
          <input
            id="posture-scope"
            type="text"
            className={styles.fieldInput}
            value={Object.keys(scope).length > 0 ? JSON.stringify(scope) : ''}
            onChange={(e) => {
              try {
                const parsed = e.target.value ? JSON.parse(e.target.value) : {};
                onChange({ ...config, scope: parsed } as unknown as Partial<LogicConfig>);
              } catch {
                // Invalid JSON — don't update
              }
            }}
            placeholder='e.g., {"archived": false}'
          />
        </div>
      </div>
    </section>
  );
}
