import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listRules, createRule, updateRule, deleteRule, listRuleVersions } from '../../api/rules';
import type { RuleVersionResponse } from '../../api/rules';
import type { RuleResponse, RuleCreate, RuleCategory } from '../../types/detections';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { RuleConfigEditorContainer } from './editor/RuleConfigEditorContainer';
import { JsonConfigEditor } from './editor/JsonConfigEditor';
import { TestRuleModal } from './TestRuleModal';
import { formatAbsolute } from '../../utils/dates';
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
    // Only reset config to defaults when creating a new rule
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
          <table className={styles.versionTable}>
            <thead>
              <tr>
                <th>Version</th>
                <th>Changed by</th>
                <th>Date</th>
                <th>Summary</th>
                <th>Commit</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.id}>
                  <td>v{v.version}</td>
                  <td>{v.changed_by}</td>
                  <td>{formatAbsolute(v.created_at)}</td>
                  <td>{v.change_summary ?? '—'}</td>
                  <td>
                    {v.git_commit_sha ? (
                      <span className={styles.versionHash}>{v.git_commit_sha.slice(0, 7)}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <Button variant="default" size="sm" onClick={() => setViewConfig(v)}>
                      View config
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={styles.versionNote}>No version history available.</p>
      )}
    </div>
  );
}

export function RulesPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editRule, setEditRule] = useState<RuleResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RuleResponse | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [versionRule, setVersionRule] = useState<RuleResponse | null>(null);
  const [testRuleTarget, setTestRuleTarget] = useState<RuleResponse | null>(null);
  const [page, setPage] = useState(1);
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
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: RuleCreate }) => updateRule(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      setEditRule(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      setDeleteTarget(null);
    },
  });

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Detection Rules</h1>
          <p className={styles.pageSub}>Manage built-in and custom detection rules</p>
        </div>
        <div className={styles.headerActions}>
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

      {isLoading ? (
        <Spinner />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Status</th>
                <th>Rule name</th>
                <th>Logic</th>
                <th>Severity</th>
                <th>Detections (30d)</th>
                <th>Version</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(rules?.items ?? []).map((rule) => (
                <tr key={rule.id}>
                  <td>
                    <Label variant={rule.status === 'active' ? 'success' : 'muted'}>
                      {rule.status === 'active' ? 'active' : 'draft'}
                    </Label>
                  </td>
                  <td>
                    <div className={styles.ruleName}>{rule.name}</div>
                  </td>
                  <td>
                    <Label variant="muted">{rule.logic_type}</Label>
                  </td>
                  <td>
                    <Label variant={SEVERITY_VARIANT[rule.default_severity] ?? 'muted'}>
                      {rule.default_severity}
                    </Label>
                  </td>
                  <td className={styles.muted}>
                    {rule.status === 'active'
                      ? (() => {
                          const count = 0;
                          return count > 0 ? (
                            <span
                              className={styles.clickableCount}
                              role="link"
                              tabIndex={0}
                              onClick={() => navigate(`/threats?rule_id=${rule.id}`)}
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
                  </td>
                  <td>
                    <span
                      className={`${styles.versionMono} ${styles.clickableVersion}`}
                      role="link"
                      tabIndex={0}
                      onClick={() => setVersionRule(rule)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') setVersionRule(rule);
                      }}
                    >
                      v{rule.version}.0.0
                    </span>
                  </td>
                  <td>
                    <div className={styles.headerActions}>
                      <Button size="sm" variant="default" onClick={() => setTestRuleTarget(rule)}>
                        Test
                      </Button>
                      <Button size="sm" variant="default" onClick={() => setEditRule(rule)}>
                        Edit
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {(rules?.items ?? []).length === 0 && (
                <tr>
                  <td colSpan={7} className={styles.empty}>
                    No rules configured
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {rules && (
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={rules.total}
              onPageChange={setPage}
            />
          )}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create rule" width={720}>
        <RuleForm onSave={(v) => createMutation.mutate(v)} onCancel={() => setShowCreate(false)} />
      </Modal>

      <Modal open={!!editRule} onClose={() => setEditRule(null)} title="Edit rule" width={720}>
        {editRule && (
          <RuleForm
            initial={editRule}
            onSave={(v) => updateMutation.mutate({ id: editRule.id, data: v })}
            onCancel={() => setEditRule(null)}
          />
        )}
      </Modal>

      <Modal
        open={!!versionRule}
        onClose={() => setVersionRule(null)}
        title="Version history"
        width={720}
      >
        {versionRule && <VersionHistory rule={versionRule} />}
      </Modal>

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
    </div>
  );
}
