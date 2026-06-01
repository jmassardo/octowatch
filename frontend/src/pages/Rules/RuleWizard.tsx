import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { createRule } from '../../api/rules';
import type { RuleCreate, RuleCategory } from '../../types/detections';
import { InfoTooltip } from '../../components/common/InfoTooltip';
import { Button } from '../../components/primitives/Button';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { JsonConfigEditor } from './editor/JsonConfigEditor';
import { RuleConfigEditorContainer } from './editor/RuleConfigEditorContainer';
import { getSampleEvent } from './sampleEvent';
import styles from './Rules.module.css';

const CATEGORIES: RuleCategory[] = [
  'access_control',
  'data_exfiltration',
  'defense_evasion',
  'incident_response',
  'policy_violation',
  'posture_change',
  'posture_degradation',
  'privilege_escalation',
  'supply_chain',
  'exfiltration',
  'account_compromise',
  'secret_leakage',
  'branch_protection_bypass',
  'pat_abuse',
  'impossible_travel',
  'off_hours_anomaly',
  'other',
];
const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'] as const;
const CONFIDENCES = ['high', 'medium', 'low'] as const;
const LOGIC_TYPES = ['threshold', 'pattern', 'sequence', 'statistical', 'posture'] as const;
const STEP_LABELS = ['Template', 'Basic Info', 'Matching', 'Logic', 'Test', 'Review'];
const SCRATCH_TEMPLATE = '__scratch__';

interface LibraryRule {
  readonly name: string;
  readonly slug: string;
  readonly description: string;
  readonly category: RuleCategory;
  readonly default_severity: string;
  readonly default_confidence: string;
  readonly logic_type: string;
  readonly logic_config: Record<string, unknown>;
}

interface LibraryCategory {
  readonly category: string;
  readonly display_name: string;
  readonly rules: readonly LibraryRule[];
}

interface LibraryResponse {
  readonly categories: readonly LibraryCategory[];
  readonly total_rules: number;
}

function getDefaultConfig(logicType: string): Record<string, unknown> {
  switch (logicType) {
    case 'pattern':
      return { action_filters: [], field_conditions: [], confidence: 0.5 };
    case 'threshold':
      return {
        action_filters: [],
        field_conditions: [],
        threshold: 10,
        time_window_minutes: 60,
        aggregation_key: 'actor',
        confidence: 0.5,
      };
    case 'sequence':
      return {
        action_filters: [],
        sequence_steps: [
          { action: '', min_count: 1 },
          { action: '', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
      };
    case 'statistical':
      return {
        action_filters: [],
        field_conditions: [],
        time_window_minutes: 60,
        confidence: 0.65,
        x_config: {
          engine: 'impossible_travel',
          distance_threshold_km: 500,
          speed_threshold_kmh: 900,
          suppress_proxy_ips: true,
        },
      };
    case 'posture':
      return {
        entity_type: 'org',
        check_type: 'field_value',
        field: '',
        operator: 'eq',
        value: '',
        confidence: 0.85,
      };
    default:
      return {};
  }
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function asOptionalString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function fetchTemplates(): Promise<LibraryResponse> {
  return api.get<LibraryResponse>('/rules/library');
}

function FieldLabel({
  htmlFor,
  label,
  tooltip,
}: {
  htmlFor?: string;
  label: string;
  tooltip: string;
}) {
  return (
    <label className={styles.formLabelWithTooltip} htmlFor={htmlFor}>
      <span>{label}</span>
      <InfoTooltip content={tooltip} label={`${label} help`} />
    </label>
  );
}

export function RuleWizard({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [selectedTemplate, setSelectedTemplate] = useState(SCRATCH_TEMPLATE);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugEdited, setSlugEdited] = useState(false);
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<RuleCategory>('other');
  const [severity, setSeverity] = useState<(typeof SEVERITIES)[number]>('medium');
  const [confidence, setConfidence] = useState<(typeof CONFIDENCES)[number]>('medium');
  const [logicType, setLogicType] = useState<(typeof LOGIC_TYPES)[number]>('threshold');
  const [logicConfig, setLogicConfig] = useState<Record<string, unknown>>(
    getDefaultConfig('threshold'),
  );
  const [mitreInput, setMitreInput] = useState('');
  const [mitreTags, setMitreTags] = useState<string[]>([]);
  const [actionPatternInput, setActionPatternInput] = useState('');
  const [actionPatterns, setActionPatterns] = useState<string[]>([]);
  const [namespaceFilter, setNamespaceFilter] = useState('');
  const [sampleEventJson, setSampleEventJson] = useState(() =>
    JSON.stringify(getSampleEvent(category), null, 2),
  );
  const [stepError, setStepError] = useState<string | null>(null);
  const [showAdvancedEditor, setShowAdvancedEditor] = useState(false);

  const {
    data: library,
    isLoading: templatesLoading,
    isError: templatesError,
    refetch,
  } = useQuery({
    queryKey: ['rule-library', 'wizard'],
    queryFn: fetchTemplates,
  });

  const templates = useMemo(
    () => library?.categories.flatMap((item) => item.rules) ?? [],
    [library],
  );

  const mergedLogicConfig = useMemo(() => {
    const nextConfig = { ...logicConfig };
    if (actionPatterns.length > 0) {
      nextConfig.action_filters = actionPatterns;
    } else {
      delete nextConfig.action_filters;
    }
    if (namespaceFilter.trim()) {
      nextConfig.namespace_filter = namespaceFilter.trim();
    } else {
      delete nextConfig.namespace_filter;
    }
    if (mitreTags.length > 0) {
      nextConfig.mitre_tags = mitreTags;
    } else {
      delete nextConfig.mitre_tags;
    }
    return nextConfig;
  }, [actionPatterns, logicConfig, mitreTags, namespaceFilter]);

  function applyAdvancedConfig(nextConfig: Record<string, unknown>) {
    setLogicConfig(nextConfig);
    setActionPatterns(asStringArray(nextConfig.action_filters));
    setNamespaceFilter(asOptionalString(nextConfig.namespace_filter));
    setMitreTags(asStringArray(nextConfig.mitre_tags));
  }

  const createMutation = useMutation({
    mutationFn: (mode: 'active' | 'monitoring') => {
      const payload: RuleCreate = {
        name: name.trim(),
        slug: slug.trim(),
        description: description.trim() || undefined,
        category,
        default_severity: severity,
        default_confidence: confidence,
        logic_type: logicType,
        logic_config: mergedLogicConfig,
        enabled: true,
        status: 'active',
        mode,
      };
      return createRule(payload);
    },
    onSuccess: () => {
      onCreated();
    },
    onError: (error) => {
      setStepError(error instanceof Error ? error.message : 'Failed to create rule');
    },
  });

  function applyTemplate(template?: LibraryRule) {
    if (!template) {
      setSelectedTemplate(SCRATCH_TEMPLATE);
      setName('');
      setSlug('');
      setSlugEdited(false);
      setDescription('');
      setCategory('other');
      setSampleEventJson(JSON.stringify(getSampleEvent('other'), null, 2));
      setSeverity('medium');
      setConfidence('medium');
      setLogicType('threshold');
      setLogicConfig(getDefaultConfig('threshold'));
      setMitreTags([]);
      setActionPatterns([]);
      setNamespaceFilter('');
      setShowAdvancedEditor(false);
      setStepError(null);
      return;
    }

    setSelectedTemplate(template.slug);
    setName(template.name);
    setSlug(template.slug);
    setSlugEdited(false);
    setDescription(template.description);
    setCategory(template.category);
    setSampleEventJson(JSON.stringify(getSampleEvent(template.category), null, 2));
    setSeverity(
      (SEVERITIES.includes(template.default_severity as (typeof SEVERITIES)[number])
        ? template.default_severity
        : 'medium') as (typeof SEVERITIES)[number],
    );
    setConfidence(
      (CONFIDENCES.includes(template.default_confidence as (typeof CONFIDENCES)[number])
        ? template.default_confidence
        : 'medium') as (typeof CONFIDENCES)[number],
    );
    setLogicType(
      (LOGIC_TYPES.includes(template.logic_type as (typeof LOGIC_TYPES)[number])
        ? template.logic_type
        : 'threshold') as (typeof LOGIC_TYPES)[number],
    );
    setLogicConfig(template.logic_config);
    setActionPatterns(asStringArray(template.logic_config.action_filters));
    setNamespaceFilter(asOptionalString(template.logic_config.namespace_filter));
    setMitreTags(asStringArray(template.logic_config.mitre_tags));
    setShowAdvancedEditor(false);
    setStepError(null);
  }

  function addActionPattern() {
    const value = actionPatternInput.trim();
    if (!value || actionPatterns.includes(value)) {
      setActionPatternInput('');
      return;
    }
    setActionPatterns((prev) => [...prev, value]);
    setActionPatternInput('');
  }

  function addMitreTag() {
    const value = mitreInput.trim().toUpperCase();
    if (!value || mitreTags.includes(value)) {
      setMitreInput('');
      return;
    }
    setMitreTags((prev) => [...prev, value]);
    setMitreInput('');
  }

  function validateStep(step: number): boolean {
    if (step === 1 && (!name.trim() || !slug.trim())) {
      setStepError('Name and slug are required before continuing.');
      return false;
    }
    if (step === 2 && actionPatterns.length === 0 && !namespaceFilter.trim()) {
      setStepError('Add at least one action pattern or a namespace filter.');
      return false;
    }
    setStepError(null);
    return true;
  }

  function handleNext() {
    if (!validateStep(currentStep)) {
      return;
    }
    setCurrentStep((prev) => Math.min(prev + 1, STEP_LABELS.length - 1));
  }

  function handleBack() {
    setStepError(null);
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  }

  function renderTemplateStep() {
    return (
      <div className={styles.wizardTemplateGrid}>
        <div
          className={`${styles.wizardTemplateCard} ${selectedTemplate === SCRATCH_TEMPLATE ? styles.wizardTemplateCardSelected : ''}`}
          onClick={() => applyTemplate()}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              applyTemplate();
            }
          }}
          role="button"
          tabIndex={0}
        >
          <div className={styles.wizardTemplateName}>Start from scratch</div>
          <div className={styles.wizardTemplateDesc}>
            Build a custom detection rule with guided setup across all rule fields.
          </div>
        </div>
        {templates.map((template) => (
          <div
            key={template.slug}
            className={`${styles.wizardTemplateCard} ${selectedTemplate === template.slug ? styles.wizardTemplateCardSelected : ''}`}
            onClick={() => applyTemplate(template)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                applyTemplate(template);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <div className={styles.wizardTemplateName}>{template.name}</div>
            <div className={styles.wizardTemplateDesc}>{template.description}</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <Label variant="muted">{template.logic_type}</Label>
              <Label variant="muted">{template.default_severity}</Label>
            </div>
          </div>
        ))}
      </div>
    );
  }

  function renderBasicInfoStep() {
    return (
      <div className={styles.ruleForm}>
        <div className={styles.formRow}>
          <FieldLabel
            htmlFor="wizard-name"
            label="Name"
            tooltip="A human-readable name for this detection rule. Example: 'Impossible Travel Login'"
          />
          <input
            id="wizard-name"
            className={styles.formInput}
            value={name}
            onChange={(event) => {
              const nextName = event.target.value;
              setName(nextName);
              if (!slugEdited) {
                setSlug(slugify(nextName));
              }
            }}
            placeholder="Impossible Travel Login"
          />
        </div>
        <div className={styles.formRow}>
          <FieldLabel
            htmlFor="wizard-slug"
            label="Slug"
            tooltip="A unique URL-safe identifier for this rule. Auto-generated from the name. Example: 'impossible-travel-login'"
          />
          <input
            id="wizard-slug"
            className={styles.formInput}
            value={slug}
            onChange={(event) => {
              setSlugEdited(true);
              setSlug(slugify(event.target.value));
            }}
            placeholder="impossible-travel-login"
          />
        </div>
        <div className={styles.formRow}>
          <FieldLabel
            htmlFor="wizard-description"
            label="Description"
            tooltip="Explain what this rule detects and why it matters. Shown in alerts and reports."
          />
          <textarea
            id="wizard-description"
            className={styles.formTextarea}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
          />
        </div>
        <div className={styles.formRowGrid}>
          <div className={styles.formRow}>
            <FieldLabel
              htmlFor="wizard-category"
              label="Category"
              tooltip="The threat category this rule belongs to. Helps organize rules and route alerts. Example: 'account_compromise' for credential-related detections."
            />
            <select
              id="wizard-category"
              className={styles.formSelect}
              value={category}
              onChange={(event) => {
                const nextCategory = event.target.value as RuleCategory;
                setCategory(nextCategory);
                setSampleEventJson(JSON.stringify(getSampleEvent(nextCategory), null, 2));
              }}
            >
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {item.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.formRow}>
            <FieldLabel
              htmlFor="wizard-severity"
              label="Severity"
              tooltip="Default severity level for detections. **critical** = immediate response, **high** = urgent, **medium** = investigate soon, **low** = informational."
            />
            <select
              id="wizard-severity"
              className={styles.formSelect}
              value={severity}
              onChange={(event) => setSeverity(event.target.value as (typeof SEVERITIES)[number])}
            >
              {SEVERITIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.formRow}>
            <FieldLabel
              htmlFor="wizard-confidence"
              label="Confidence"
              tooltip="How confident detections from this rule are. **high** = low false positive rate, **medium** = some tuning needed, **low** = noisy, needs validation."
            />
            <select
              id="wizard-confidence"
              className={styles.formSelect}
              value={confidence}
              onChange={(event) =>
                setConfidence(event.target.value as (typeof CONFIDENCES)[number])
              }
            >
              {CONFIDENCES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className={styles.formRow}>
          <FieldLabel
            htmlFor="wizard-mitre"
            label="MITRE tags"
            tooltip="MITRE ATT&CK technique IDs relevant to this detection. Example: T1078 (Valid Accounts), T1098 (Account Manipulation)."
          />
          <div className={styles.headerActions}>
            <input
              id="wizard-mitre"
              className={styles.formInput}
              value={mitreInput}
              onChange={(event) => setMitreInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  addMitreTag();
                }
              }}
              placeholder="T1078"
            />
            <Button type="button" size="sm" onClick={addMitreTag}>
              Add
            </Button>
          </div>
          {mitreTags.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              {mitreTags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  className={styles.wizardTemplateCard}
                  style={{
                    padding: '4px 8px',
                    display: 'inline-flex',
                    gap: 8,
                    alignItems: 'center',
                  }}
                  onClick={() => setMitreTags((prev) => prev.filter((item) => item !== tag))}
                >
                  <span>{tag}</span>
                  <span aria-hidden="true">×</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  function renderMatchingStep() {
    return (
      <div className={styles.ruleForm}>
        <div className={styles.formRow}>
          <FieldLabel
            htmlFor="wizard-action-pattern"
            label="Action patterns"
            tooltip="GitHub audit log action strings to match. Use exact action names from the audit log. Example: 'auth.login', 'repo.clone', 'org.update_member'."
          />
          <div className={styles.headerActions}>
            <input
              id="wizard-action-pattern"
              className={styles.formInput}
              value={actionPatternInput}
              onChange={(event) => setActionPatternInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  addActionPattern();
                }
              }}
              placeholder="auth.login"
              list="wizard-action-suggestions"
            />
            <datalist id="wizard-action-suggestions">
              <option value="auth.login" />
              <option value="repo.clone" />
              <option value="git.push" />
              <option value="repos.create" />
              <option value="org.update_member" />
            </datalist>
            <Button type="button" size="sm" onClick={addActionPattern}>
              Add
            </Button>
          </div>
          {actionPatterns.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              {actionPatterns.map((pattern) => (
                <button
                  key={pattern}
                  type="button"
                  className={styles.wizardTemplateCard}
                  style={{
                    padding: '4px 8px',
                    display: 'inline-flex',
                    gap: 8,
                    alignItems: 'center',
                  }}
                  onClick={() =>
                    setActionPatterns((prev) => prev.filter((item) => item !== pattern))
                  }
                >
                  <span>{pattern}</span>
                  <span aria-hidden="true">×</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className={styles.formRow}>
          <FieldLabel
            htmlFor="wizard-namespace-filter"
            label="Namespace filter"
            tooltip="Limit matching to events from a specific audit log namespace. Example: 'github.enterprise.audit'."
          />
          <input
            id="wizard-namespace-filter"
            className={styles.formInput}
            value={namespaceFilter}
            onChange={(event) => setNamespaceFilter(event.target.value)}
            placeholder="github.enterprise.audit"
          />
        </div>
        <div className={styles.backtestSummary}>
          Configure the common event-level filters before tuning the detection logic in the next
          step.
        </div>
      </div>
    );
  }

  function renderLogicStep() {
    return (
      <div className={styles.ruleForm}>
        <div className={styles.formRow}>
          <FieldLabel
            htmlFor="wizard-logic-type"
            label="Logic type"
            tooltip="The detection engine: **threshold** = count events in window, **pattern** = match field conditions, **sequence** = ordered steps, **statistical** = anomaly detection, **posture** = config drift."
          />
          <select
            id="wizard-logic-type"
            className={styles.formSelect}
            value={logicType}
            onChange={(event) => {
              const nextType = event.target.value as (typeof LOGIC_TYPES)[number];
              setLogicType(nextType);
              setLogicConfig((prev) => {
                const nextDefault = getDefaultConfig(nextType);
                return Object.keys(prev).length > 0 ? { ...nextDefault, ...prev } : nextDefault;
              });
            }}
          >
            {LOGIC_TYPES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.editorSection}>
          <div className={styles.editorSectionHeader}>Logic Configuration</div>
          <RuleConfigEditorContainer
            logicType={logicType}
            config={mergedLogicConfig}
            onChange={setLogicConfig}
          />
        </div>
      </div>
    );
  }

  function renderTestStep() {
    return (
      <div className={styles.ruleForm}>
        <div className={styles.backtestSummary}>
          Full live testing is available after the rule is created. Review or edit the sample event
          below to validate the expected shape now.
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel} htmlFor="wizard-sample-event">
            Sample event payload
          </label>
          <textarea
            id="wizard-sample-event"
            className={styles.testJsonEditor}
            value={sampleEventJson}
            onChange={(event) => setSampleEventJson(event.target.value)}
            rows={14}
            spellCheck={false}
          />
        </div>
      </div>
    );
  }

  function renderReviewStep() {
    return (
      <div className={styles.wizardSummary}>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Template</div>
          <div className={styles.wizardSummaryValue}>
            {selectedTemplate === SCRATCH_TEMPLATE ? 'Start from scratch' : selectedTemplate}
          </div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Name</div>
          <div className={styles.wizardSummaryValue}>{name}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Slug</div>
          <div className={styles.wizardSummaryValue}>{slug}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Category</div>
          <div className={styles.wizardSummaryValue}>{category}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Severity</div>
          <div className={styles.wizardSummaryValue}>{severity}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Confidence</div>
          <div className={styles.wizardSummaryValue}>{confidence}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>MITRE Tags</div>
          <div className={styles.wizardSummaryValue}>{mitreTags.join(', ') || '—'}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Actions</div>
          <div className={styles.wizardSummaryValue}>{actionPatterns.join(', ') || '—'}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Namespace</div>
          <div className={styles.wizardSummaryValue}>{namespaceFilter || '—'}</div>
        </div>
        <div className={styles.wizardSummaryRow}>
          <div className={styles.wizardSummaryLabel}>Logic Type</div>
          <div className={styles.wizardSummaryValue}>{logicType}</div>
        </div>
        <div className={styles.formRow}>
          <div className={styles.reviewActions}>
            <label className={styles.formLabel}>Logic config preview</label>
            <Button
              type="button"
              variant="default"
              size="sm"
              onClick={() => setShowAdvancedEditor((current) => !current)}
            >
              {showAdvancedEditor ? 'Hide Advanced Edit' : 'Advanced Edit'}
            </Button>
          </div>
          {showAdvancedEditor ? (
            <JsonConfigEditor config={mergedLogicConfig} onChange={applyAdvancedConfig} />
          ) : (
            <pre className={styles.testJsonEditor}>
              {JSON.stringify(mergedLogicConfig, null, 2)}
            </pre>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wizard}>
      <div>
        <div className={styles.wizardStepper} aria-label="Rule wizard progress">
          {STEP_LABELS.map((label, index) => (
            <div
              key={label}
              className={`${styles.wizardStep} ${index < currentStep ? styles.wizardStepDone : ''} ${index === currentStep ? styles.wizardStepActive : ''}`}
            />
          ))}
        </div>
        <div className={styles.wizardStepLabels}>
          {STEP_LABELS.map((label, index) => (
            <div
              key={label}
              className={`${styles.wizardStepLabel} ${index === currentStep ? styles.wizardStepLabelActive : ''}`}
            >
              {index + 1}. {label}
            </div>
          ))}
        </div>
      </div>

      {stepError && <ErrorBanner message={stepError} />}

      <div className={styles.wizardContent}>
        {currentStep === 0 &&
          (templatesLoading ? (
            <Spinner />
          ) : templatesError ? (
            <ErrorBanner message="Failed to load rule templates" onRetry={() => refetch()} />
          ) : (
            renderTemplateStep()
          ))}
        {currentStep === 1 && renderBasicInfoStep()}
        {currentStep === 2 && renderMatchingStep()}
        {currentStep === 3 && renderLogicStep()}
        {currentStep === 4 && renderTestStep()}
        {currentStep === 5 && renderReviewStep()}
      </div>

      <div className={styles.wizardNav}>
        <div>
          {currentStep === 0 ? (
            <Button type="button" variant="default" onClick={onClose}>
              Cancel
            </Button>
          ) : (
            <Button type="button" variant="default" onClick={handleBack}>
              Back
            </Button>
          )}
        </div>
        <div className={styles.headerActions}>
          {currentStep < STEP_LABELS.length - 1 ? (
            <Button type="button" variant="primary" onClick={handleNext}>
              Next
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant="default"
                onClick={() => createMutation.mutate('monitoring')}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? 'Creating…' : 'Create as Monitoring'}
              </Button>
              <Button
                type="button"
                variant="primary"
                onClick={() => createMutation.mutate('active')}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? 'Creating…' : 'Create as Active'}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
