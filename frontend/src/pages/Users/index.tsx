import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listRoleAssignments,
  createRoleAssignment,
  deleteRoleAssignment,
  listRoles,
  getActiveSessions,
} from '../../api/admin';
import type { RoleAssignment, RoleAssignmentCreate, ActiveSession } from '../../types/admin';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Users.module.css';

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function roleLabel(roleId: number, scopeType: string): { text: string; variant: 'danger' | 'accent' | 'muted' } {
  const name = `${scopeType}`.toLowerCase();
  if (name.includes('admin') || roleId === 1) return { text: 'Admin', variant: 'danger' };
  if (name.includes('write') || name.includes('analyst') || roleId === 2) return { text: 'Write', variant: 'accent' };
  return { text: 'Read', variant: 'muted' };
}

function sessionRoleVariant(role: string): 'danger' | 'accent' | 'muted' {
  const r = role.toLowerCase();
  if (r.includes('admin') || r === 'sys_admin') return 'danger';
  if (r.includes('write') || r.includes('analyst')) return 'accent';
  return 'muted';
}

function sessionRoleLabel(role: string): string {
  const r = role.toLowerCase();
  if (r.includes('admin') || r === 'sys_admin') return 'Admin';
  if (r.includes('write') || r.includes('analyst')) return 'Analyst';
  return 'Read';
}

function mfaVariant(mfaEnabled: boolean): 'success' | 'attention' {
  return mfaEnabled ? 'success' : 'attention';
}

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function teamSlugFromAssignment(a: RoleAssignment): string {
  if (a.github_team_slug) return `@${a.github_team_slug}`;
  if (a.scope_value) return `@${a.scope_value}`;
  return `@org/${a.github_login}`;
}

/* ------------------------------------------------------------------ */
/*  Add-mapping form                                                  */
/* ------------------------------------------------------------------ */

function AddMappingForm({
  roles,
  onSave,
  onCancel,
}: {
  roles: string[];
  onSave: (v: RoleAssignmentCreate) => void;
  onCancel: () => void;
}) {
  const [login, setLogin] = useState('');
  const [role, setRole] = useState(roles[0] ?? 'viewer');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({ github_login: login, role_name: role, scope_type: 'global' });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.addForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>GitHub login</label>
        <input
          className={styles.formInput}
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          required
          placeholder="octocat"
          autoFocus
        />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Role</label>
        <select
          className={styles.formSelect}
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          {roles.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" type="submit">Add mapping</Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Edit-mapping form                                                 */
/* ------------------------------------------------------------------ */

function EditMappingForm({
  assignment,
  roles,
  onSave,
  onCancel,
}: {
  assignment: RoleAssignment;
  roles: string[];
  onSave: (v: RoleAssignmentCreate) => void;
  onCancel: () => void;
}) {
  const roleMap: Record<number, string> = { 1: 'admin', 2: 'analyst' };
  const [login, setLogin] = useState(assignment.github_login);
  const [role, setRole] = useState(roleMap[assignment.role_id] ?? roles[0] ?? 'viewer');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({ github_login: login, role_name: role, scope_type: 'global' });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.addForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>GitHub login</label>
        <input
          className={styles.formInput}
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          required
          placeholder="octocat"
          autoFocus
        />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Role</label>
        <select
          className={styles.formSelect}
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          {roles.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" type="submit">Save</Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                              */
/* ------------------------------------------------------------------ */

export function UsersPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [showAdd, setShowAdd] = useState(false);
  const [editTarget, setEditTarget] = useState<RoleAssignment | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RoleAssignment | null>(null);
  const [sessionUser, setSessionUser] = useState<ActiveSession | null>(null);

  const { data: assignments, isLoading, isError, refetch } = useQuery({
    queryKey: ['role-assignments'],
    queryFn: listRoleAssignments,
  });

  const { data: roleDefs } = useQuery({
    queryKey: ['roles'],
    queryFn: listRoles,
  });

  const {
    data: sessions,
    isLoading: sessionsLoading,
    isError: sessionsError,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: ['active-sessions'],
    queryFn: getActiveSessions,
  });

  const roles = roleDefs?.map((r) => r.name) ?? ['viewer', 'analyst', 'admin'];

  const createMutation = useMutation({
    mutationFn: createRoleAssignment,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['role-assignments'] }); setShowAdd(false); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteRoleAssignment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['role-assignments'] }); setDeleteTarget(null); },
  });

  const editMutation = useMutation({
    mutationFn: async ({ oldId, data }: { oldId: number; data: RoleAssignmentCreate }) => {
      await deleteRoleAssignment(oldId);
      return createRoleAssignment(data);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['role-assignments'] }); setEditTarget(null); },
  });

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Users &amp; roles</h1>
          <p className={styles.pageSub}>Manage team mappings and active user sessions</p>
        </div>
        <Button variant="primary" onClick={() => setShowAdd(true)}>Add mapping</Button>
      </div>

      {isError && <ErrorBanner message="Failed to load role assignments" onRetry={() => refetch()} />}

      {/* ---- Section 1: Team mappings ---- */}
      <section>
        <h2 className={styles.sectionTitle}>Team mappings</h2>
        {isLoading ? (
          <Spinner />
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>GitHub team</th>
                  <th>OctoWatch role</th>
                  <th>Mapped by</th>
                  <th>Last synced</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(assignments ?? []).map((a) => {
                  const rl = roleLabel(a.role_id, a.scope_type);
                  return (
                    <tr key={a.id}>
                      <td>
                        <span className={styles.teamName}>{teamSlugFromAssignment(a)}</span>
                      </td>
                      <td>
                        <Label variant={rl.variant}>{rl.text}</Label>
                      </td>
                      <td>
                        <span
                          className={`${styles.mention} ${styles.clickableMention}`}
                          role="link"
                          tabIndex={0}
                          onClick={() => navigate(`/events?actor=${a.granted_by}`)}
                          onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/events?actor=${a.granted_by}`); }}
                        >
                          @{a.granted_by}
                        </span>
                      </td>
                      <td className={styles.muted}>{formatRelativeTime(a.granted_at)}</td>
                      <td style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                        <Button size="sm" onClick={() => setEditTarget(a)}>Edit</Button>
                        <button
                          onClick={() => setDeleteTarget(a)}
                          aria-label={`Remove mapping for ${a.github_login}`}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', fontSize: 16, padding: '2px 6px', borderRadius: 4 }}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {(assignments ?? []).length === 0 && (
                  <tr><td colSpan={5} className={styles.empty}>No team mappings configured</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ---- Section 2: Active users ---- */}
      <section>
        <h2 className={styles.sectionTitle}>Active users</h2>
        {sessionsError && <ErrorBanner message="Failed to load active sessions" onRetry={() => refetchSessions()} />}
        {sessionsLoading ? (
          <Spinner />
        ) : (sessions ?? []).length === 0 ? (
          <div className={styles.empty}>No active sessions in the last 24 hours</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Last active</th>
                  <th>MFA</th>
                  <th>Sessions</th>
                </tr>
              </thead>
              <tbody>
                {(sessions ?? []).map((u) => (
                  <tr key={u.login}>
                    <td>
                      <span
                        className={`${styles.mention} ${styles.clickableMention}`}
                        role="link"
                        tabIndex={0}
                        onClick={() => navigate(`/events?actor=${u.login}`)}
                        onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/events?actor=${u.login}`); }}
                      >
                        @{u.login}
                      </span>
                    </td>
                    <td>
                      <Label variant={sessionRoleVariant(u.role)}>{sessionRoleLabel(u.role)}</Label>
                    </td>
                    <td className={styles.muted}>{u.last_active_at ? formatRelativeTime(u.last_active_at) : '—'}</td>
                    <td>
                      <Label variant={mfaVariant(u.mfa_enabled)}>{u.mfa_enabled ? 'enabled' : 'pending'}</Label>
                    </td>
                    <td>
                      <span
                        className={styles.clickableSession}
                        role="button"
                        tabIndex={0}
                        onClick={() => setSessionUser(u)}
                        onKeyDown={(e) => { if (e.key === 'Enter') setSessionUser(u); }}
                      >
                        {u.session_count}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add role mapping">
        <AddMappingForm
          roles={roles}
          onSave={(v) => createMutation.mutate(v)}
          onCancel={() => setShowAdd(false)}
        />
      </Modal>

      <Modal open={!!editTarget} onClose={() => setEditTarget(null)} title="Edit role mapping">
        {editTarget && (
          <EditMappingForm
            assignment={editTarget}
            roles={roles}
            onSave={(v) => editMutation.mutate({ oldId: editTarget.id, data: v })}
            onCancel={() => setEditTarget(null)}
          />
        )}
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Remove mapping"
        message={deleteTarget ? `Remove role mapping for "${deleteTarget.github_login}"?` : ''}
        confirmLabel="Remove"
        confirmVariant="danger"
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
      />

      <Modal open={!!sessionUser} onClose={() => setSessionUser(null)} title={sessionUser ? `Sessions — @${sessionUser.login}` : 'Sessions'}>
        {sessionUser && (
          <dl className={styles.sessionDetail}>
            <div>
              <dt>User</dt>
              <dd>@{sessionUser.login}</dd>
            </div>
            <div>
              <dt>Active sessions</dt>
              <dd>{sessionUser.session_count}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{sessionRoleLabel(sessionUser.role)}</dd>
            </div>
            <div>
              <dt>Last active</dt>
              <dd>{sessionUser.last_active_at ? formatRelativeTime(sessionUser.last_active_at) : '—'}</dd>
            </div>
            <div>
              <dt>MFA</dt>
              <dd>{sessionUser.mfa_enabled ? 'enabled' : 'pending'}</dd>
            </div>
            <p className={styles.sessionNote}>
              Detailed session data including IP addresses and user agents requires GitHub API integration.
            </p>
          </dl>
        )}
      </Modal>
    </div>
  );
}
