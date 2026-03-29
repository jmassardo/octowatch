import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listSettings,
  updateSetting,
  deleteSetting,
  getSettingsAuditTrail,
} from '../../api/setup';
import type { AppSetting, SettingAuditEntry } from '../../api/setup';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Settings.module.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const CATEGORIES = ['All', 'GitHub', 'Security', 'Storage', 'Notifications', 'System'] as const;
type Category = (typeof CATEGORIES)[number];

const SLUG_TO_TAB: Record<string, Category | 'Audit'> = {
  all: 'All',
  github: 'GitHub',
  security: 'Security',
  storage: 'Storage',
  notifications: 'Notifications',
  system: 'System',
  audit: 'Audit',
};

const TAB_TO_SLUG: Record<string, string> = Object.fromEntries(
  Object.entries(SLUG_TO_TAB).map(([slug, tab]) => [tab, slug]),
);

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function sensitivityClass(sensitivity: string): string {
  if (sensitivity === 'critical') return styles.sensitivityCritical;
  if (sensitivity === 'sensitive') return styles.sensitivitySensitive;
  return styles.sensitivityNormal;
}

function auditActionClass(action: string): string {
  const a = action.toLowerCase();
  if (a.includes('create') || a === 'set') return styles.auditActionCreate;
  if (a.includes('update') || a.includes('change')) return styles.auditActionUpdate;
  if (a.includes('delete') || a.includes('revert')) return styles.auditActionDelete;
  return '';
}

/* ------------------------------------------------------------------ */
/*  Edit Form                                                          */
/* ------------------------------------------------------------------ */

function EditSettingForm({
  setting,
  onSave,
  onCancel,
}: {
  setting: AppSetting;
  onSave: (value: string, description?: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState('');
  const [description, setDescription] = useState(setting.description ?? '');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    onSave(value.trim(), description.trim() || undefined);
  }

  return (
    <form onSubmit={handleSubmit} className={styles.editForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Key</label>
        <input className={styles.formInput} value={setting.key} disabled />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Current value (masked)</label>
        <input className={styles.formInput} value={setting.value} disabled />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="setting-value">New value</label>
        <input
          id="setting-value"
          className={styles.formInput}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Enter new value"
          required
          autoFocus
        />
        <span className={styles.formHint}>
          The previous value will be replaced. Sensitive values are stored encrypted.
        </span>
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="setting-description">Description (optional)</label>
        <input
          id="setting-description"
          className={styles.formInput}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Short description of this setting"
        />
      </div>
      <div className={styles.formActions}>
        <Button type="button" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" type="submit" disabled={!value.trim()}>Save</Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Audit Trail Table                                                  */
/* ------------------------------------------------------------------ */

function AuditTrailTable() {
  const { data: entries, isLoading, isError, refetch } = useQuery({
    queryKey: ['settings', 'audit-trail'],
    queryFn: getSettingsAuditTrail,
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load audit trail" onRetry={() => refetch()} />;

  if (!entries || entries.length === 0) {
    return <div className={styles.empty}>No audit trail entries yet</div>;
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Setting</th>
            <th>Action</th>
            <th>Changed by</th>
            <th>Old value</th>
            <th>New value</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry: SettingAuditEntry, idx: number) => (
            <tr key={`${entry.setting_key}-${entry.created_at}-${idx}`}>
              <td className={styles.settingKey}>{entry.setting_key}</td>
              <td>
                <span className={`${styles.auditAction} ${auditActionClass(entry.action)}`}>
                  {entry.action}
                </span>
              </td>
              <td>{entry.changed_by}</td>
              <td className={styles.settingValue}>{entry.old_value_masked ?? '—'}</td>
              <td className={styles.settingValue}>{entry.new_value_masked ?? '—'}</td>
              <td className={styles.settingMeta}>{formatDateTime(entry.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Settings Page                                                      */
/* ------------------------------------------------------------------ */

export function SettingsPage() {
  const qc = useQueryClient();
  const { tab: tabSlug } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const activeTab: Category | 'Audit' = SLUG_TO_TAB[tabSlug ?? 'all'] ?? 'All';
  const [editTarget, setEditTarget] = useState<AppSetting | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AppSetting | null>(null);

  const { data: settings, isLoading, isError, refetch } = useQuery({
    queryKey: ['settings'],
    queryFn: listSettings,
  });

  const updateMutation = useMutation({
    mutationFn: ({ key, value, description }: { key: string; value: string; description?: string }) =>
      updateSetting(key, value, description),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] });
      qc.invalidateQueries({ queryKey: ['settings', 'audit-trail'] });
      setEditTarget(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (key: string) => deleteSetting(key),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] });
      qc.invalidateQueries({ queryKey: ['settings', 'audit-trail'] });
      setDeleteTarget(null);
    },
  });

  const filteredSettings = settings?.filter(
    (s: AppSetting) => activeTab === 'All' || s.category.toLowerCase() === (activeTab as string).toLowerCase(),
  ) ?? [];

  const isCategory = activeTab !== 'Audit';

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Settings</h1>
          <p className={styles.pageSub}>Manage application settings and view the audit trail</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className={styles.tabs}>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            className={activeTab === cat ? styles.tabActive : styles.tab}
            onClick={() => navigate(`/settings/${TAB_TO_SLUG[cat]}`)}
          >
            {cat}
          </button>
        ))}
        <button
          className={activeTab === 'Audit' ? styles.tabActive : styles.tab}
          onClick={() => navigate('/settings/audit')}
        >
          Audit Trail
        </button>
      </div>

      {/* Content */}
      {activeTab === 'Audit' ? (
        <AuditTrailTable />
      ) : (
        <>
          {isError && <ErrorBanner message="Failed to load settings" onRetry={() => refetch()} />}

          {isLoading ? (
            <Spinner />
          ) : isCategory && filteredSettings.length === 0 ? (
            <div className={styles.empty}>
              No settings in {activeTab === 'All' ? 'any category' : `the ${activeTab} category`}
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Value</th>
                    <th>Sensitivity</th>
                    <th>Description</th>
                    <th>Updated</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSettings.map((s: AppSetting) => (
                    <tr key={s.key}>
                      <td className={styles.settingKey}>{s.key}</td>
                      <td className={styles.settingValue}>{s.value}</td>
                      <td>
                        <span className={sensitivityClass(s.sensitivity)}>{s.sensitivity}</span>
                      </td>
                      <td className={styles.settingDescription}>{s.description ?? '—'}</td>
                      <td className={styles.settingMeta}>
                        {s.updated_by} · {formatDateTime(s.updated_at)}
                      </td>
                      <td>
                        <div className={styles.cellActions}>
                          <Button size="sm" onClick={() => setEditTarget(s)}>Edit</Button>
                          <Button size="sm" variant="danger" onClick={() => setDeleteTarget(s)}>Reset</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Edit modal */}
      <Modal open={!!editTarget} onClose={() => setEditTarget(null)} title={`Edit: ${editTarget?.key ?? ''}`}>
        {editTarget && (
          <EditSettingForm
            setting={editTarget}
            onSave={(value, description) =>
              updateMutation.mutate({ key: editTarget.key, value, description })
            }
            onCancel={() => setEditTarget(null)}
          />
        )}
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Reset setting"
        message={
          deleteTarget
            ? `Reset "${deleteTarget.key}" to its default (environment variable) value? This action is logged.`
            : ''
        }
        confirmLabel="Reset to default"
        confirmVariant="danger"
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.key)}
      />
    </div>
  );
}
