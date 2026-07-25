import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listRules,
  getRule,
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
import { RuleWizard } from './RuleWizard';
import { BacktestPanel } from './BacktestPanel';
import { RuleAnalytics } from './RuleAnalytics';
import { formatAbsolute } from '../../utils/dates';
import { useQueryParamInt, useQueryParam } from '../../hooks/useQueryParam';
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
const MODES = ['active', 'monitoring', 'disabled'] as const;
const SORT_OPTIONS = [
  { value: 'created_at', label: 'Created' },
  { value: 'name', label: 'Name' },
  { value: 'severity', label: 'Severity' },
  { value: 'logic_type', label: 'Logic type' },
  { value: 'status', label: 'Status' },
] as const;

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
        <div className={styles.versionHeaderRow}>
          <span className={styles.versionHeaderLabel}>Version {viewConfig.version} — Config</span>
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

function RuleDetailContent({ rule }: { rule: RuleResponse }) {
  return (
    <div className={styles.detailPanel}>
      <div className={styles.detailSection}>
        <div className={styles.detailGrid}>
          <div>
            <div className={styles.detailLabel}>Name</div>
            <div className={styles.detailValue}>{rule.name}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Slug</div>
            <div className={styles.detailValueMono}>{rule.slug}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Category</div>
            <div className={styles.detailValue}>{rule.category.replace(/_/g, ' ')}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Logic type</div>
            <div className={styles.detailValue}>
              <Label variant="muted">{rule.logic_type}</Label>
            </div>
          </div>
          <div>
            <div className={styles.detailLabel}>Severity</div>
            <div className={styles.detailValue}>
              <Label variant={SEVERITY_VARIANT[rule.default_severity] ?? 'muted'}>
                {rule.default_severity}
              </Label>
            </div>
          </div>
          <div>
            <div className={styles.detailLabel}>Confidence</div>
            <div className={styles.detailValue}>{rule.default_confidence}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Status</div>
            <div className={styles.detailValue}>{rule.status}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Mode</div>
            <div className={styles.detailValue}>{rule.mode}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Enabled</div>
            <div className={styles.detailValue}>{rule.enabled ? 'Yes' : 'No'}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Version</div>
            <div className={styles.detailValueMono}>v{rule.version}.0.0</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Created by</div>
            <div className={styles.detailValue}>{rule.created_by}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Updated by</div>
            <div className={styles.detailValue}>{rule.updated_by ?? '—'}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Created</div>
            <div className={styles.detailValue}>{formatAbsolute(rule.created_at)}</div>
          </div>
          <div>
            <div className={styles.detailLabel}>Updated</div>
            <div className={styles.detailValue}>{formatAbsolute(rule.updated_at)}</div>
          </div>
        </div>
      </div>

      <div className={styles.detailSection}>
        <div className={styles.detailLabel}>Description</div>
        <div className={styles.detailValue}>{rule.description || 'No description provided.'}</div>
      </div>

      <div className={styles.detailSection}>
        <div className={styles.detailLabel}>Logic configuration</div>
        <JsonConfigEditor config={rule.logic_config} onChange={() => {}} readOnly />
      </div>
    </div>
  );
}

export function RulesPage() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const { ruleId: ruleIdParam } = useParams<{ ruleId?: string }>();
  const [drawerView] = useQueryParam('view', '');
  const [showWizard, setShowWizard] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RuleResponse | null>(null);
  const [page, setPage] = useQueryParamInt('page', 1);
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<number>>(new Set());
  const [filterSeverity, setFilterSeverity] = useState<string>('');
  const [filterLogicType, setFilterLogicType] = useState<string>('');
  const [filterMode, setFilterMode] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [sortField, setSortField] = useState<string>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const navigate = useNavigate();

  const PAGE_SIZE = 25;

  const {
    data: rules,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: [
      'rules',
      page,
      filterSeverity,
      filterLogicType,
      filterMode,
      searchTerm,
      sortField,
      sortOrder,
    ],
    queryFn: () =>
      listRules({
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        severity: filterSeverity || undefined,
        logic_type: filterLogicType || undefined,
        mode: filterMode || undefined,
        search: searchTerm || undefined,
        sort: sortField || undefined,
        order: sortOrder || undefined,
      }),
  });

  const deepLinkRuleId = ruleIdParam ? parseInt(ruleIdParam, 10) : null;
  const { data: deepLinkRule } = useQuery({
    queryKey: ['rule', deepLinkRuleId],
    queryFn: () => getRule(deepLinkRuleId!),
    enabled: deepLinkRuleId !== null && !isNaN(deepLinkRuleId),
  });

  const routeRule = deepLinkRule ?? rules?.items.find((rule) => rule.id === deepLinkRuleId) ?? null;
  const activeDrawerView = routeRule ? drawerView || 'detail' : '';
  const selectedRule = activeDrawerView === 'detail' ? routeRule : null;
  const versionRule = activeDrawerView === 'versions' ? routeRule : null;
  const analyticsRule = activeDrawerView === 'analytics' ? routeRule : null;
  const backtestRuleTarget = activeDrawerView === 'backtest' ? routeRule : null;
  const testRuleTarget = activeDrawerView === 'test' ? routeRule : null;

  function openRuleDrawer(rule: RuleResponse, view: string = 'detail') {
    setIsEditing(false);
    navigate(`/rules/${rule.id}${view !== 'detail' ? `?view=${view}` : ''}`, { replace: true });
  }

  function closeRuleDrawer() {
    setIsEditing(false);
    navigate('/rules' + (page > 1 ? `?page=${page}` : ''), { replace: true });
  }

  function applyFilters(update: () => void) {
    update();
    setPage(1);
    setSelectedRuleIds(new Set());
  }

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: RuleCreate }) => updateRule(id, data),
    onSuccess: (rule) => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      setIsEditing(false);
      navigate(`/rules/${rule.id}`, { replace: true });
      showToast('Rule updated successfully', 'success');
    },
    onError: () => {
      showToast('Failed to update rule', 'error');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: (_, deletedId) => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      if (deepLinkRuleId === deletedId) {
        closeRuleDrawer();
      }
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

  const hasFilters =
    searchTerm !== '' ||
    filterSeverity !== '' ||
    filterLogicType !== '' ||
    filterMode !== '' ||
    sortField !== 'created_at' ||
    sortOrder !== 'desc';

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <PageHeader
          title="Detection Rules"
          description="Configure automated threat detection patterns"
          showHelp
        />
        <div className={styles.headerActions}>
          <Button variant="primary" size="sm" onClick={() => setShowWizard(true)}>
            New Rule
          </Button>
        </div>
      </div>

      <div className={styles.filterBar}>
        <div className={styles.filterSearchRow}>
          <input
            className={styles.formInput}
            value={searchTerm}
            onChange={(event) => applyFilters(() => setSearchTerm(event.target.value))}
            placeholder="Search by name, slug, or description"
            aria-label="Search rules"
          />
        </div>
        <div className={styles.filterControls}>
          <select
            className={styles.formSelect}
            value={filterSeverity}
            onChange={(event) => applyFilters(() => setFilterSeverity(event.target.value))}
            aria-label="Filter by severity"
          >
            <option value="">All severities</option>
            {SEVERITIES.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
          <select
            className={styles.formSelect}
            value={filterLogicType}
            onChange={(event) => applyFilters(() => setFilterLogicType(event.target.value))}
            aria-label="Filter by logic type"
          >
            <option value="">All logic types</option>
            {LOGIC_TYPES.map((logicType) => (
              <option key={logicType} value={logicType}>
                {logicType}
              </option>
            ))}
          </select>
          <select
            className={styles.formSelect}
            value={filterMode}
            onChange={(event) => applyFilters(() => setFilterMode(event.target.value))}
            aria-label="Filter by mode"
          >
            <option value="">All modes</option>
            {MODES.map((mode) => (
              <option key={mode} value={mode}>
                {mode}
              </option>
            ))}
          </select>
          <select
            className={styles.formSelect}
            value={sortField}
            onChange={(event) => applyFilters(() => setSortField(event.target.value))}
            aria-label="Sort field"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                Sort by {option.label}
              </option>
            ))}
          </select>
          <Button
            variant="default"
            size="sm"
            onClick={() => applyFilters(() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc'))}
          >
            {sortOrder === 'asc' ? 'Ascending' : 'Descending'}
          </Button>
          {hasFilters && (
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                setSearchTerm('');
                setFilterSeverity('');
                setFilterLogicType('');
                setFilterMode('');
                setSortField('created_at');
                setSortOrder('desc');
                setSelectedRuleIds(new Set());
                setPage(1);
              }}
            >
              Clear filters
            </Button>
          )}
        </div>
      </div>

      {isError && <ErrorBanner message="Failed to load rules" onRetry={() => refetch()} />}

      {selectedRuleIds.size > 0 && (
        <div className={styles.bulkBar}>
          <span className={styles.bulkCount}>{selectedRuleIds.size} selected</span>
          <div className={styles.headerActions}>
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
                render: (rule) => (
                  <Label variant={rule.status === 'active' ? 'success' : 'muted'}>
                    {rule.status}
                  </Label>
                ),
              },
              {
                key: 'mode',
                header: 'Mode',
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
                render: (rule) => <div className={styles.ruleName}>{rule.name}</div>,
              },
              {
                key: 'logic',
                header: 'Logic',
                helpText:
                  'The detection logic type — threshold, anomaly, or pattern. Determines how audit events are analyzed.',
                render: (rule) => <Label variant="muted">{rule.logic_type}</Label>,
              },
              {
                key: 'severity',
                header: 'Severity',
                helpText:
                  'Default severity assigned to detections created by this rule. Can be critical, high, medium, low, or info.',
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
                                navigate(`/threats/open?rule_id=${rule.id}`);
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  navigate(`/threats/open?rule_id=${rule.id}`);
                                }
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
                render: (rule) => (
                  <span
                    className={`${styles.versionMono} ${styles.clickableVersion}`}
                    role="link"
                    tabIndex={0}
                    onClick={(e) => {
                      e.stopPropagation();
                      openRuleDrawer(rule, 'versions');
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        openRuleDrawer(rule, 'versions');
                      }
                    }}
                  >
                    v{rule.version}.0.0
                  </span>
                ),
              },
            ]}
            data={rules?.items ? [...rules.items] : []}
            rowKey={(rule) => rule.id}
            onRowClick={(rule) => openRuleDrawer(rule)}
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

      <Drawer
        open={!!selectedRule}
        onClose={closeRuleDrawer}
        title={
          selectedRule
            ? isEditing
              ? `Edit rule: ${selectedRule.name}`
              : `Rule detail: ${selectedRule.name}`
            : 'Rule detail'
        }
      >
        {selectedRule && (
          <div className={styles.detailPanel}>
            <div className={styles.detailActions}>
              <Button
                size="sm"
                variant="primary"
                onClick={() => setIsEditing((current) => !current)}
              >
                {isEditing ? 'Cancel edit' : 'Edit'}
              </Button>
              <Button size="sm" variant="danger" onClick={() => setDeleteTarget(selectedRule)}>
                Delete
              </Button>
              <Button
                size="sm"
                variant="default"
                onClick={() => openRuleDrawer(selectedRule, 'analytics')}
              >
                Analytics
              </Button>
              <Button
                size="sm"
                variant="default"
                onClick={() => openRuleDrawer(selectedRule, 'backtest')}
              >
                Backtest
              </Button>
              <Button
                size="sm"
                variant="default"
                onClick={() => openRuleDrawer(selectedRule, 'test')}
              >
                Test
              </Button>
              <Button
                size="sm"
                variant="default"
                onClick={() => openRuleDrawer(selectedRule, 'versions')}
              >
                Version History
              </Button>
            </div>
            {isEditing ? (
              <RuleForm
                initial={selectedRule}
                onSave={(v) => updateMutation.mutate({ id: selectedRule.id, data: v })}
                onCancel={() => setIsEditing(false)}
              />
            ) : (
              <RuleDetailContent rule={selectedRule} />
            )}
          </div>
        )}
      </Drawer>

      <Drawer open={!!versionRule} onClose={closeRuleDrawer} title="Version history">
        {versionRule && <VersionHistory rule={versionRule} />}
      </Drawer>

      <Drawer
        open={!!analyticsRule}
        onClose={closeRuleDrawer}
        title={`Analytics: ${analyticsRule?.name ?? ''}`}
      >
        {analyticsRule && <RuleAnalytics rule={analyticsRule} />}
      </Drawer>

      <Drawer
        open={!!backtestRuleTarget}
        onClose={closeRuleDrawer}
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

      <TestRuleModal rule={testRuleTarget} onClose={closeRuleDrawer} />
    </div>
  );
}
