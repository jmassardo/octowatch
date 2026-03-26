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
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Avatar } from '../../components/primitives/Avatar';
import styles from './Users.module.css';

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
    onSave({ github_login: login, role });
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
          <p className={styles.pageSub}>Map GitHub logins to application roles</p>
        </div>
        <Button variant="primary" onClick={() => setShowAdd(true)}>Add mapping</Button>
      </div>

      {isError && <ErrorBanner message="Failed to load role assignments" onRetry={() => refetch()} />}

      {isLoading ? (
        <Spinner />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Assigned by</th>
                <th>Assigned at</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(assignments ?? []).map((a) => (
                <tr key={a.id}>
                  <td>
                    <div className={styles.userCell}>
                      <Avatar username={a.github_login} />
                      <span className={styles.login}>{a.github_login}</span>
                    </div>
                  </td>
                  <td>
                    <span className={styles.rolePill}>{a.role}</span>
                  </td>
                  <td className={styles.muted}>{a.assigned_by}</td>
                  <td className={styles.muted}>{new Date(a.assigned_at).toLocaleString()}</td>
                  <td>
                    <Button size="sm" variant="danger" onClick={() => setDeleteTarget(a)}>Remove</Button>
                  </td>
                </tr>
              ))}
              {(assignments ?? []).length === 0 && (
                <tr><td colSpan={5} className={styles.empty}>No role assignments configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

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
