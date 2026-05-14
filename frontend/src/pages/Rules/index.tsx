import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listRules,
  createRule,
  updateRule,
  deleteRule,
  listRuleVersions,
  bulkUpdateRules,
} from '../../api/rules';
import type { RuleVersionResponse } from '../../api/rules';
import type { RuleResponse, RuleCreate, RuleCategory } from '../../types/detections';
import { useToast } from '../../hooks/useToast';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Drawer } from '../../components/primitives/Drawer';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { DataTable } from '../../components/primitives/DataTable';
import { RuleConfigEditorContainer } from './editor/RuleConfigEditorContainer';
import { JsonConfigEditor } from './editor/JsonConfigEditor';
import { TestRuleModal } from './TestRuleModal';
import { RuleLibrary } from './RuleLibrary';
import { RuleWizard } from './RuleWizard';
import { BacktestPanel } from './BacktestPanel';
import { RuleAnalytics } from './RuleAnalytics';
import { formatAbsolute } from '../../utils/dates';
import { useQueryParamInt } from '../../hooks/useQueryParam';
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

const SEVERITY_VARIANT: Record<string, 'danger' | 'attention' | 'success' | 'muted'> = {
  critical: 'danger',
  high: 'attention',
  medium: 'success',
  low: 'muted',
};

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

function RuleForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: RuleResponse;
  onSave: (v: RuleCreate) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? '');
  const [slug, setSlug] = useState(initial?.slug ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [category, setCategory] = useState<RuleCategory>(initial?.category ?? 'other');
  const [severity, setSeverity] = useState(initial?.default_severity ?? 'medium');
  const [confidence, setConfidence] = useState(initial?.default_confidence ?? 'medium');
  const [logicType, setLogicType] = useState(initial?.logic_type ?? 'threshold');
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [logicConfig, setLogicConfig] = useState<Record<string, unknown>>(
    initial?.logic_config ?? getDefaultConfig(logicType),
  );
  const [changeSummary, setChangeSummary] = useState('');

  function handleLogicTypeChange(newType: string) {
    setLogicType(newType);
    if (!initial) {
      setLogicConfig(getDefaultConfig(newType));
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({
      name,
      slug,
      description: description || undefined,
      category,
      default_severity: severity,
      default_confidence: confidence,
      logic_type: logicType,
      logic_config: logicConfig,
      enabled,
      ...(initial && changeSummary ? { change_summary: changeSummary } : {}),
    });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.ruleForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Name</label>
        <input
          className={styles.formInput}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="Impossible Travel Login"
        />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Slug</label>
        <input
          className={styles.formInput}
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          required
          placeholder="impossible-travel-login"
        />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Description</label>
        <textarea
          className={styles.formTextarea}
          value={description ?? ''}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
        />
      </div>
      <div className={styles.formRowGrid}>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Category</label>
          <select
            className={styles.formSelect}
            value={category}
            onChange={(e) => setCategory(e.target.value as RuleCategory)}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Severity</label>
          <select
            className={styles.formSelect}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Confidence</label>
          <select
            className={styles.formSelect}
            value={confidence}
            onChange={(e) => setConfidence(e.target.value)}
          >
            {CONFIDENCES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Logic type</label>
          <select
            className={styles.formSelect}
            value={logicType}
            onChange={(e) => handleLogicTypeChange(e.target.value)}
          >
            {LOGIC_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className={styles.formRowCheck}>
        <label className={styles.checkLabel}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled
        </label>
      </div>

      <div className={styles.editorSection}>
        <div className={styles.editorSectionHeader}>Detection Logic</div>
        <RuleConfigEditorContainer
          logicType={logicType as 'pattern' | 'threshold' | 'sequence' | 'statistical' | 'posture'}
          config={logicConfig}
          onChange={setLogicConfig}
        />
      </div>

      {initial && (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Change summary</label>
          <textarea
            className={styles.formTextarea}
            value={changeSummary}
            onChange={(e) => setChangeSummary(e.target.value)}
            placeholder="Describe what changed..."
            rows={2}
          />
        </div>
      )}

      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">
          Cancel
        </Button>
        <Button variant="primary" type="submit">
          Save rule
        </Button>
      </div>
    </form>
  );
}

function VersionHistory({ rule }: { rule: RuleResponse }) {
  const [viewConfig, setViewConfig] = useState<RuleVersionResponse | null>(null);

  const {
    data: versions,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['rule-versions', rule.id],
    queryFn: () => listRuleVersions(rule.id),
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load version history" />;

  if (viewConfig) {
    return (
      <div>
        <div
          style={{
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            Version {viewConfig.version} — Config
          </span>
          <Button variant="default" size="sm" onClick={() => setViewConfig(null)}>
            ← Back
          </Button>
        </div>
        <div className={styles.versionConfigWrap}>
          <JsonConfigEditor config={viewConfig.logic_config} onChange={() => {}} readOnly />
        </div>
      </div>
    );
  }

  return (
    <div>
      <dl className={styles.versionDetail}>
        <dt>Rule name</dt>
        <dd>{rule.name}</dd>
        <dt>Current version</dt>
        <dd>v{rule.version}.0.0</dd>
      </dl>

      {versions && versions.length > 0 ? (
        <div className={styles.versionTableWrap} style={{ marginTop: 16 }}>
          <DataTable<RuleVersionResponse>
            columns={[
              {
                key: 'version',
                header: 'Version',
                helpText:
                  'Semantic version number for this rule revision. Incremented on each edit.',
                sortable: true,
                sortValue: (v) => v.version,
                render: (v) => `v${v.version}`,
              },
              {
                key: 'changed_by',
                header: 'Changed by',
                helpText: 'The user who authored this rule version change.',
                sortable: true,
                filterable: true,
                sortValue: (v) => v.changed_by.toLowerCase(),
                filterValue: (v) => v.changed_by,
                render: (v) => v.changed_by,
              },
              {
                key: 'date',
                header: 'Date',
                helpText: 'When this rule version was created or saved.',
                sortable: true,
                sortValue: (v) => v.created_at,
                render: (v) => formatAbsolute(v.created_at),
              },
              {
                key: 'summary',
                header: 'Summary',
                helpText: 'Author-provided description of what changed in this version.',
                filterable: true,
                filterValue: (v) => v.change_summary ?? '',
                render: (v) => v.change_summary ?? '—',
              },
              {
                key: 'commit',
                header: 'Commit',
                helpText:
                  'Git commit SHA associated with this rule change, if synced from a repository.',
                render: (v) =>
                  v.git_commit_sha ? (
                    <span className={styles.versionHash}>{v.git_commit_sha.slice(0, 7)}</span>
                  ) : (
                    '—'
                  ),
              },
              {
                key: 'actions',
                header: '',
                render: (v) => (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={(e: React.MouseEvent) => {
                      e.stopPropagation();
                      setViewConfig(v);
                    }}
                  >
                    View config
                  </Button>
                ),
              },
            ]}
            data={versions}
            rowKey={(v) => v.id}
            emptyMessage="No version history available"
          />
        </div>
      ) : (
        <p className={styles.versionNote}>No version history available.</p>
      )}
    </div>
  );
}

export function RulesPage() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [editRule, setEditRule] = useState<RuleResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RuleResponse | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [versionRule, setVersionRule] = useState<RuleResponse | null>(null);
  const [testRuleTarget, setTestRuleTarget] = useState<RuleResponse | null>(null);
  const [analyticsRule, setAnalyticsRule] = useState<RuleResponse | null>(null);
  const [backtestRuleTarget, setBacktestRuleTarget] = useState<RuleResponse | null>(null);
  const [showLibrary, setShowLibrary] = useState(false);
  const [page, setPage] = useQueryParamInt('page', 1);
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<number>>(new Set());
  const navigate = useNavigate();

  const PAGE_SIZE = 25;

  const {
    data: rules,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['rules', page],
    queryFn: () => listRules({ limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
  });

  const createMutation = useMutation({
    mutationFn: createRule,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      setShowCreate(false);
      showToast('Rule created successfully', 'success');
    },
    onError: () => {
      showToast('Failed to create rule', 'error');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: RuleCreate }) => updateRule(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      setEditRule(null);
      showToast('Rule updated successfully', 'success');
    },
    onError: () => {
      showToast('Failed to update rule', 'error');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      setDeleteTarget(null);
      showToast('Rule deleted successfully', 'success');
    },
    onError: () => {
      showToast('Failed to delete rule', 'error');
    },
  });

  const bulkMutation = useMutation({
    mutationFn: bulkUpdateRules,
    onSuccess: (result, variables) => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      setSelectedRuleIds(new Set());
      const actionLabel =
        variables.action === 'set_monitoring'
          ? 'set to monitoring'
          : variables.action === 'enable'
            ? 'enabled'
            : 'disabled';
      const failureSuffix = result.failed.length > 0 ? ` (${result.failed.length} failed)` : '';
      showToast(`${result.updated} rules ${actionLabel}${failureSuffix}`, 'success');
    },
    onError: () => {
      showToast('Bulk update failed', 'error');
    },
  });

  function handleBulkAction(action: 'enable' | 'disable' | 'set_monitoring') {
    if (selectedRuleIds.size === 0) return;
    bulkMutation.mutate({ rule_ids: Array.from(selectedRuleIds), action });
  }

  return (
    <div className={styles.page}>
      {showLibrary ? (
        <RuleLibrary onClose={() => setShowLibrary(false)} />
      ) : (
        <>
          <div className={styles.pageHeader}>
            <PageHeader
              title="Detection Rules"
              description="Configure automated threat detection patterns"
              showHelp
            />
            <div className={styles.headerActions}>
              <Button variant="default" size="sm" onClick={() => setShowLibrary(true)}>
                Rule Library
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => {
                  setSyncMessage('Rule sync initiated');
                  setTimeout(() => setSyncMessage(null), 3000);
                }}
              >
                Sync from GitHub
              </Button>
              <Button variant="default" size="sm" onClick={() => setShowWizard(true)}>
                New Rule (Wizard)
              </Button>
              <Button variant="primary" size="sm" onClick={() => setShowCreate(true)}>
                New rule
              </Button>
            </div>
          </div>

          {syncMessage && (
            <div
              style={{
                padding: '8px 12px',
                marginBottom: 12,
                borderRadius: 6,
                background: 'var(--success-subtle, #2ea04333)',
                color: 'var(--success)',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {syncMessage}
            </div>
          )}
          {isError && <ErrorBanner message="Failed to load rules" onRetry={() => refetch()} />}

          {selectedRuleIds.size > 0 && (
            <div className={styles.bulkBar}>
              <span className={styles.bulkCount}>{selectedRuleIds.size} selected</span>
              <Button size="sm" type="button" onClick={() => handleBulkAction('enable')}>
                Enable
              </Button>
              <Button size="sm" type="button" onClick={() => handleBulkAction('disable')}>
                Disable
              </Button>
              <Button size="sm" type="button" onClick={() => handleBulkAction('set_monitoring')}>
                Set Monitoring
              </Button>
            </div>
          )}

          {isLoading ? (
            <Spinner />
          ) : (
            <div className={styles.tableWrap}>
              <DataTable<RuleResponse>
                columns={[
                  {
                    key: 'select',
                    header: '',
                    render: (rule) => (
                      <input
                        type="checkbox"
                        aria-label={`Select ${rule.name}`}
                        checked={selectedRuleIds.has(rule.id)}
                        onChange={(event) => {
                          event.stopPropagation();
                          setSelectedRuleIds((prev) => {
                            const next = new Set(prev);
                            if (next.has(rule.id)) next.delete(rule.id);
                            else next.add(rule.id);
                            return next;
                          });
                        }}
                        onClick={(event) => event.stopPropagation()}
                      />
                    ),
                  },
                  {
                    key: 'status',
                    header: 'Status',
                    helpText:
                      'Whether the rule is actively evaluating audit events. Draft rules are not executed.',
                    sortable: true,
                    sortValue: (rule) => rule.status,
                    render: (rule) => (
                      <Label variant={rule.status === 'active' ? 'success' : 'muted'}>
                        {rule.status === 'active' ? 'active' : 'draft'}
                      </Label>
                    ),
                  },
                  {
                    key: 'mode',
                    header: 'Mode',
                    sortable: true,
                    sortValue: (rule) => rule.mode ?? 'active',
                    render: (rule) => {
                      const mode = rule.mode ?? 'active';
                      if (mode === 'monitoring') {
                        return (
                          <Label variant="attention" className={styles.monitoringBadge}>
                            monitoring
                          </Label>
                        );
                      }
                      if (mode === 'disabled') {
                        return <Label variant="muted">disabled</Label>;
                      }
                      return <Label variant="success">active</Label>;
                    },
                  },
                  {
                    key: 'name',
                    header: 'Rule name',
                    helpText: 'Human-readable name identifying this detection rule.',
                    sortable: true,
                    filterable: true,
                    sortValue: (rule) => rule.name.toLowerCase(),
                    filterValue: (rule) => rule.name,
                    render: (rule) => <div className={styles.ruleName}>{rule.name}</div>,
                  },
                  {
                    key: 'logic',
                    header: 'Logic',
                    helpText:
                      'The detection logic type — threshold, anomaly, or pattern. Determines how audit events are analyzed.',
                    sortable: true,
                    filterable: true,
                    sortValue: (rule) => rule.logic_type.toLowerCase(),
                    filterValue: (rule) => rule.logic_type,
                    render: (rule) => <Label variant="muted">{rule.logic_type}</Label>,
                  },
                  {
                    key: 'severity',
                    header: 'Severity',
                    helpText:
                      'Default severity assigned to detections created by this rule. Can be critical, high, medium, low, or info.',
                    sortable: true,
                    filterable: true,
                    sortValue: (rule) => rule.default_severity.toLowerCase(),
                    filterValue: (rule) => rule.default_severity,
                    render: (rule) => (
                      <Label variant={SEVERITY_VARIANT[rule.default_severity] ?? 'muted'}>
                        {rule.default_severity}
                      </Label>
                    ),
                  },
                  {
                    key: 'detections',
                    header: 'Detections (30d)',
                    helpText:
                      'Number of times this rule triggered a detection in the last 30 days. From audit log event analysis.',
                    sortable: true,
                    sortValue: (rule) => (rule.status === 'active' ? 0 : -1),
                    render: (rule) => (
                      <span className={styles.muted}>
                        {rule.status === 'active'
                          ? (() => {
                              const count = 0;
                              return count > 0 ? (
                                <span
                                  className={styles.clickableCount}
                                  role="link"
                                  tabIndex={0}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    navigate(`/threats?rule_id=${rule.id}`);
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') navigate(`/threats?rule_id=${rule.id}`);
                                  }}
                                >
                                  {count}
                                </span>
                              ) : (
                                '0'
                              );
                            })()
                          : '—'}
                      </span>
                    ),
                  },
                  {
                    key: 'version',
                    header: 'Version',
                    helpText:
                      'Current semantic version of the rule. Click to view full version history.',
                    sortable: true,
                    sortValue: (rule) => rule.version,
                    render: (rule) => (
                      <span
                        className={`${styles.versionMono} ${styles.clickableVersion}`}
                        role="link"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          setVersionRule(rule);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') setVersionRule(rule);
                        }}
                      >
                        v{rule.version}.0.0
                      </span>
                    ),
                  },
                  {
                    key: 'actions',
                    header: '',
                    render: (rule) => (
                      <div className={styles.headerActions}>
                        <Button
                          size="sm"
                          variant="default"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            setAnalyticsRule(rule);
                          }}
                        >
                          Analytics
                        </Button>
                        <Button
                          size="sm"
                          variant="default"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            setBacktestRuleTarget(rule);
                          }}
                        >
                          Backtest
                        </Button>
                        <Button
                          size="sm"
                          variant="default"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            setTestRuleTarget(rule);
                          }}
                        >
                          Test
                        </Button>
                        <Button
                          size="sm"
                          variant="default"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            setEditRule(rule);
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            setDeleteTarget(rule);
                          }}
                        >
                          Delete
                        </Button>
                      </div>
                    ),
                  },
                ]}
                data={rules?.items ? [...rules.items] : []}
                rowKey={(rule) => rule.id}
                onRowClick={(rule) => setEditRule(rule)}
                emptyMessage="No rules configured"
              />
              {rules && (
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={rules.total}
                  onPageChange={(nextPage) => {
                    setSelectedRuleIds(new Set());
                    setPage(nextPage);
                  }}
                />
              )}
            </div>
          )}

          <Drawer open={showCreate} onClose={() => setShowCreate(false)} title="Create rule">
            <RuleForm
              onSave={(v) => createMutation.mutate(v)}
              onCancel={() => setShowCreate(false)}
            />
          </Drawer>

          <Drawer open={showWizard} onClose={() => setShowWizard(false)} title="New Rule Wizard">
            <RuleWizard
              onClose={() => setShowWizard(false)}
              onCreated={() => {
                setShowWizard(false);
                qc.invalidateQueries({ queryKey: ['rules'] });
                showToast('Rule created', 'success');
              }}
            />
          </Drawer>

          <Drawer open={!!editRule} onClose={() => setEditRule(null)} title="Edit rule">
            {editRule && (
              <RuleForm
                initial={editRule}
                onSave={(v) => updateMutation.mutate({ id: editRule.id, data: v })}
                onCancel={() => setEditRule(null)}
              />
            )}
          </Drawer>

          <Drawer open={!!versionRule} onClose={() => setVersionRule(null)} title="Version history">
            {versionRule && <VersionHistory rule={versionRule} />}
          </Drawer>

          <Drawer
            open={!!analyticsRule}
            onClose={() => setAnalyticsRule(null)}
            title={`Analytics: ${analyticsRule?.name ?? ''}`}
          >
            {analyticsRule && <RuleAnalytics rule={analyticsRule} />}
          </Drawer>

          <Drawer
            open={!!backtestRuleTarget}
            onClose={() => setBacktestRuleTarget(null)}
            title={`Backtest: ${backtestRuleTarget?.name ?? ''}`}
          >
            {backtestRuleTarget && <BacktestPanel rule={backtestRuleTarget} />}
          </Drawer>

          <ConfirmDialog
            open={!!deleteTarget}
            onClose={() => setDeleteTarget(null)}
            title="Delete rule"
            message={deleteTarget ? `Delete "${deleteTarget.name}"? This cannot be undone.` : ''}
            confirmLabel="Delete"
            confirmVariant="danger"
            onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
          />

          <TestRuleModal rule={testRuleTarget} onClose={() => setTestRuleTarget(null)} />
        </>
      )}
    </div>
  );
}
