import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listRules, createRule, updateRule, updateRuleStatus, deleteRule } from '../../api/rules';
import type { RuleResponse, RuleCreate, RuleCategory } from '../../types/detections';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Rules.module.css';

const CATEGORIES: RuleCategory[] = [
  'exfiltration', 'account_compromise', 'privilege_escalation', 'secret_leakage',
  'supply_chain', 'branch_protection_bypass', 'pat_abuse', 'impossible_travel',
  'off_hours_anomaly', 'other',
];
const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'] as const;
const CONFIDENCES = ['high', 'medium', 'low'] as const;
const LOGIC_TYPES = ['threshold', 'pattern', 'sequence', 'statistical'] as const;

const SEVERITY_VARIANT: Record<string, 'danger' | 'attention' | 'success' | 'muted'> = {
  critical: 'danger',
  high: 'attention',
  medium: 'success',
  low: 'muted',
};

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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({
      name, slug, description: description || undefined, category,
      default_severity: severity, default_confidence: confidence,
      logic_type: logicType, logic_config: initial?.logic_config ?? {},
      enabled,
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
              <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
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
              <option key={s} value={s}>{s}</option>
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
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Logic type</label>
          <select
            className={styles.formSelect}
            value={logicType}
            onChange={(e) => setLogicType(e.target.value)}
          >
            {LOGIC_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      </div>
      <div className={styles.formRowCheck}>
        <label className={styles.checkLabel}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Enabled
        </label>
      </div>
      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" type="submit">Save rule</Button>
      </div>
    </form>
  );
}

export function RulesPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editRule, setEditRule] = useState<RuleResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RuleResponse | null>(null);

  const { data: rules, isLoading, isError, refetch } = useQuery({
    queryKey: ['rules'],
    queryFn: listRules,
  });

  const createMutation = useMutation({
    mutationFn: createRule,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rules'] }); setShowCreate(false); },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: RuleCreate }) => updateRule(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rules'] }); setEditRule(null); },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateRuleStatus(id, enabled ? 'active' : 'draft', enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rules'] }); setDeleteTarget(null); },
  });

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Detection rules</h1>
          <p className={styles.pageSub}>Configure what patterns trigger security alerts</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate(true)}>Create rule</Button>
      </div>

      {isError && <ErrorBanner message="Failed to load rules" onRetry={() => refetch()} />}

      {isLoading ? (
        <Spinner />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Category</th>
                <th>Severity</th>
                <th>Enabled</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(rules?.items ?? []).map((rule) => (
                <tr key={rule.id}>
                  <td>
                    <div className={styles.ruleName}>{rule.name}</div>
                    <div className={styles.ruleSlug}>{rule.slug}</div>
                  </td>
                  <td><Label variant="muted">{rule.category.replace(/_/g, ' ')}</Label></td>
                  <td><Label variant={SEVERITY_VARIANT[rule.default_severity] ?? 'muted'}>{rule.default_severity}</Label></td>
                  <td>
                    <button
                      className={[styles.toggle, rule.enabled ? styles.toggleOn : ''].join(' ')}
                      onClick={() => statusMutation.mutate({ id: rule.id, enabled: !rule.enabled })}
                      aria-label={rule.enabled ? 'Disable rule' : 'Enable rule'}
                    >
                      <span className={styles.toggleThumb} />
                    </button>
                  </td>
                  <td className={styles.muted}>{new Date(rule.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className={styles.rowActions}>
                      <Button size="sm" variant="default" onClick={() => setEditRule(rule)}>Edit</Button>
                      <Button size="sm" variant="danger" onClick={() => setDeleteTarget(rule)}>Delete</Button>
                    </div>
                  </td>
                </tr>
              ))}
              {(rules?.items ?? []).length === 0 && (
                <tr><td colSpan={6} className={styles.empty}>No rules configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create rule">
        <RuleForm
          onSave={(v) => createMutation.mutate(v)}
          onCancel={() => setShowCreate(false)}
        />
      </Modal>

      <Modal open={!!editRule} onClose={() => setEditRule(null)} title="Edit rule">
        {editRule && (
          <RuleForm
            initial={editRule}
            onSave={(v) => updateMutation.mutate({ id: editRule.id, data: v })}
            onCancel={() => setEditRule(null)}
          />
        )}
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
    </div>
  );
}
