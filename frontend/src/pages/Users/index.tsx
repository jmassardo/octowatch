import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listRoleAssignments,
  createRoleAssignment,
  deleteRoleAssignment,
  listRoles,
} from '../../api/admin';
import type { RoleAssignment, RoleAssignmentCreate } from '../../types/admin';
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

interface ActiveUser {
  readonly login: string;
  readonly role: 'Admin' | 'Write' | 'Read';
  readonly lastActive: string;
  readonly mfa: 'enabled' | 'pending';
  readonly sessions: number;
}

const ACTIVE_USERS: readonly ActiveUser[] = [
  { login: 'jmassardo', role: 'Admin', lastActive: 'Just now', mfa: 'enabled', sessions: 3 },
  { login: 'mwestphal', role: 'Write', lastActive: '12 min ago', mfa: 'enabled', sessions: 1 },
  { login: 'skeshari', role: 'Write', lastActive: '34 min ago', mfa: 'pending', sessions: 2 },
  { login: 'jdoe-bot', role: 'Read', lastActive: '1 hr ago', mfa: 'enabled', sessions: 1 },
];

function roleLabel(roleId: number, scopeType: string): { text: string; variant: 'danger' | 'accent' | 'muted' } {
  const name = `${scopeType}`.toLowerCase();
  if (name.includes('admin') || roleId === 1) return { text: 'Admin', variant: 'danger' };
  if (name.includes('write') || name.includes('analyst') || roleId === 2) return { text: 'Write', variant: 'accent' };
  return { text: 'Read', variant: 'muted' };
}

function userRoleVariant(role: ActiveUser['role']): 'danger' | 'accent' | 'muted' {
  if (role === 'Admin') return 'danger';
  if (role === 'Write') return 'accent';
  return 'muted';
}

function mfaVariant(mfa: ActiveUser['mfa']): 'success' | 'attention' {
  return mfa === 'enabled' ? 'success' : 'attention';
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
/*  Page                                                              */
/* ------------------------------------------------------------------ */

export function UsersPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RoleAssignment | null>(null);

  const { data: assignments, isLoading, isError, refetch } = useQuery({
    queryKey: ['role-assignments'],
    queryFn: listRoleAssignments,
  });

  const { data: roleDefs } = useQuery({
    queryKey: ['roles'],
    queryFn: listRoles,
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
                        <span className={styles.mention}>@{a.granted_by}</span>
                      </td>
                      <td className={styles.muted}>{formatRelativeTime(a.granted_at)}</td>
                      <td>
                        <Button size="sm" onClick={() => setDeleteTarget(a)}>Edit</Button>
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
              {ACTIVE_USERS.map((u) => (
                <tr key={u.login}>
                  <td>
                    <span className={styles.mention}>@{u.login}</span>
                  </td>
                  <td>
                    <Label variant={userRoleVariant(u.role)}>{u.role}</Label>
                  </td>
                  <td className={styles.muted}>{u.lastActive}</td>
                  <td>
                    <Label variant={mfaVariant(u.mfa)}>{u.mfa}</Label>
                  </td>
                  <td className={styles.muted}>{u.sessions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add role mapping">
        <AddMappingForm
          roles={roles}
          onSave={(v) => createMutation.mutate(v)}
          onCancel={() => setShowAdd(false)}
        />
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
    </div>
  );
}
