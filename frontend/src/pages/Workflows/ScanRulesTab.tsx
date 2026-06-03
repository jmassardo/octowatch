import { useState } from 'react';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Drawer } from '../../components/primitives/Drawer';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import styles from './Workflows.module.css';

/* ── Built-in rules catalog ───────────────────────────────────────────────── */

interface ScanRule {
  id: string;
  name: string;
  description: string;
  severity: string;
  category: 'builtin' | 'custom';
  enabled: boolean;
  pattern?: string;
}

const BUILTIN_RULES: ScanRule[] = [
  {
    id: 'self-hosted-runner',
    name: 'Self-hosted runner detected',
    description: 'Flags jobs running on self-hosted runners which require security hardening.',
    severity: 'medium',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'excessive-secrets',
    name: 'High secret exposure',
    description: 'Flags jobs receiving 3 or more secrets (blast radius risk).',
    severity: 'high',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'moderate-secrets',
    name: 'Multiple secrets passed to job',
    description: 'Flags jobs receiving more than 1 secret for review.',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'pr-triggered-workflow',
    name: 'PR-triggered workflow',
    description: 'Flags workflows triggered from pull request context (potential code injection).',
    severity: 'medium',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'reusable-workflow-chain',
    name: 'Reusable workflow chain',
    description: 'Flags reusable workflows called by other workflows (permission inheritance).',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'slim-runner-image',
    name: 'Slim runner image',
    description: 'Flags jobs using slim runner images.',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'public-repo-workflow',
    name: 'Public repository workflow',
    description: 'Flags workflows on public repos (fork PR attack surface).',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'pat-triggered-workflow',
    name: 'PAT-triggered workflow',
    description: 'Flags workflows triggered via Personal Access Tokens.',
    severity: 'medium',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'schedule-triggered',
    name: 'Scheduled workflow',
    description: 'Flags cron-scheduled workflows (potential persistence vector).',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'bot-triggered-workflow',
    name: 'Bot-triggered workflow',
    description: 'Flags workflows triggered by bot accounts for permission review.',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'chained-workflow',
    name: 'Chained workflow (workflow_run)',
    description: 'Flags workflows triggered by other workflows (privilege escalation risk).',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'dependabot-updates',
    name: 'Dependabot auto-update tracking',
    description: 'Tracks Dependabot-triggered workflow runs.',
    severity: 'low',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'script-injection',
    name: 'Script injection via untrusted input',
    description: 'Detects use of untrusted GitHub context expressions in run: blocks.',
    severity: 'critical',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'unpinned-action',
    name: 'Unpinned action reference',
    description: 'Detects actions referenced by tag/branch instead of commit SHA.',
    severity: 'high',
    category: 'builtin',
    enabled: true,
  },
  {
    id: 'excessive-permissions',
    name: 'Excessive workflow permissions',
    description: 'Detects workflows with write-all or overly broad permission grants.',
    severity: 'high',
    category: 'builtin',
    enabled: true,
  },
];

function sevVariant(sev: string) {
  if (sev === 'critical') return 'danger' as const;
  if (sev === 'high') return 'severe' as const;
  if (sev === 'medium') return 'attention' as const;
  return 'muted' as const;
}

/* ── Component ────────────────────────────────────────────────────────────── */

export function ScanRulesTab() {
  const [rules, setRules] = useState<ScanRule[]>(() => {
    const saved = localStorage.getItem('octowatch:scan-rules-custom');
    const custom: ScanRule[] = saved ? JSON.parse(saved) : [];
    return [...BUILTIN_RULES, ...custom];
  });
  const [editingRule, setEditingRule] = useState<ScanRule | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ScanRule | null>(null);

  // Form state for editing/creating
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formSeverity, setFormSeverity] = useState('medium');
  const [formPattern, setFormPattern] = useState('');

  function openCreate() {
    setFormName('');
    setFormDesc('');
    setFormSeverity('medium');
    setFormPattern('');
    setCreatingNew(true);
  }

  function openEdit(rule: ScanRule) {
    setFormName(rule.name);
    setFormDesc(rule.description);
    setFormSeverity(rule.severity);
    setFormPattern(rule.pattern ?? '');
    setEditingRule(rule);
  }

  function saveRule() {
    if (creatingNew) {
      const newRule: ScanRule = {
        id: `custom-${crypto.randomUUID()}`,
        name: formName,
        description: formDesc,
        severity: formSeverity,
        category: 'custom',
        enabled: true,
        pattern: formPattern,
      };
      const updated = [...rules, newRule];
      setRules(updated);
      persistCustomRules(updated);
    } else if (editingRule) {
      const updated = rules.map((r) =>
        r.id === editingRule.id
          ? {
              ...r,
              name: formName,
              description: formDesc,
              severity: formSeverity,
              pattern: formPattern,
            }
          : r,
      );
      setRules(updated);
      persistCustomRules(updated);
    }
    setCreatingNew(false);
    setEditingRule(null);
  }

  function toggleRule(id: string) {
    const updated = rules.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r));
    setRules(updated);
    persistCustomRules(updated);
  }

  function deleteRule() {
    if (!deleteTarget) return;
    const updated = rules.filter((r) => r.id !== deleteTarget.id);
    setRules(updated);
    persistCustomRules(updated);
    setDeleteTarget(null);
  }

  function persistCustomRules(all: ScanRule[]) {
    const custom = all.filter((r) => r.category === 'custom');
    localStorage.setItem('octowatch:scan-rules-custom', JSON.stringify(custom));
  }

  return (
    <div>
      <div className={styles.rulesHeader}>
        <div className={styles.rulesDescription}>
          These rules define what the workflow scanner checks for. Built-in rules can be toggled
          on/off. Custom rules use regex patterns to match against workflow file contents.
        </div>
        <Button size="sm" variant="primary" onClick={openCreate}>
          + New Custom Rule
        </Button>
      </div>

      <table className={styles.findingsTable}>
        <thead>
          <tr>
            <th scope="col">Enabled</th>
            <th scope="col">Rule</th>
            <th scope="col">Severity</th>
            <th scope="col">Type</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.id} className={styles.findingRow}>
              <td>
                <input
                  type="checkbox"
                  checked={rule.enabled}
                  onChange={() => toggleRule(rule.id)}
                  aria-label={`Toggle ${rule.name}`}
                />
              </td>
              <td>
                <strong>{rule.name}</strong>
                <div style={{ fontSize: 11, color: 'var(--fg-muted)' }}>{rule.description}</div>
                {rule.pattern && (
                  <code style={{ fontSize: 10, color: 'var(--fg-muted)' }}>{rule.pattern}</code>
                )}
              </td>
              <td>
                <Label variant={sevVariant(rule.severity)}>{rule.severity}</Label>
              </td>
              <td>
                <Label variant={rule.category === 'builtin' ? 'muted' : 'accent'}>
                  {rule.category}
                </Label>
              </td>
              <td>
                <div style={{ display: 'flex', gap: 4 }}>
                  <Button size="sm" variant="default" onClick={() => openEdit(rule)}>
                    Edit
                  </Button>
                  {rule.category === 'custom' && (
                    <Button size="sm" variant="danger" onClick={() => setDeleteTarget(rule)}>
                      Delete
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Edit / Create Drawer */}
      <Drawer
        open={editingRule != null || creatingNew}
        onClose={() => {
          setEditingRule(null);
          setCreatingNew(false);
        }}
        title={creatingNew ? 'New Custom Rule' : 'Edit Rule'}
      >
        <div className={styles.drawerForm}>
          <div className={styles.formField}>
            <label>Name</label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="Rule name"
              className={styles.filterSelect}
            />
          </div>
          <div className={styles.formField}>
            <label>Description</label>
            <textarea
              value={formDesc}
              onChange={(e) => setFormDesc(e.target.value)}
              placeholder="What does this rule detect?"
              className={styles.filterSelect}
              rows={3}
              style={{ resize: 'vertical', minHeight: 60 }}
            />
          </div>
          <div className={styles.formField}>
            <label>Severity</label>
            <select
              value={formSeverity}
              onChange={(e) => setFormSeverity(e.target.value)}
              className={styles.filterSelect}
            >
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          {(creatingNew || editingRule?.category === 'custom') && (
            <div className={styles.formField}>
              <label>Regex Pattern</label>
              <input
                type="text"
                value={formPattern}
                onChange={(e) => setFormPattern(e.target.value)}
                placeholder="e.g., uses:\s*actions/checkout@(?!([a-f0-9]{40}))"
                className={styles.filterSelect}
              />
              <span style={{ fontSize: 11, color: 'var(--fg-muted)' }}>
                Matched against workflow YAML content during scans.
              </span>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <Button variant="primary" size="sm" onClick={saveRule} disabled={!formName.trim()}>
              {creatingNew ? 'Create' : 'Save'}
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                setEditingRule(null);
                setCreatingNew(false);
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      </Drawer>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteTarget != null}
        title="Delete Custom Rule"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={false}
        onConfirm={deleteRule}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
