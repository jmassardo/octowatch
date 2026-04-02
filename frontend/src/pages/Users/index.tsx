import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listRoleAssignments,
  createRoleAssignment,
  deleteRoleAssignment,
  listRoles,
  getActiveSessions,
  listSyncedTeams,
} from '../../api/admin';
import type { RoleAssignment, RoleAssignmentCreate, ActiveSession } from '../../types/admin';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { formatRelative } from '../../utils/dates';
import styles from './Users.module.css';

/* ------------------------------------------------------------------ */
/*  Role display name / badge mapping                                 */
/* ------------------------------------------------------------------ */

/** Canonical role name → human-readable display name. */
const ROLE_DISPLAY_NAMES: Record<string, string> = {
  sys_admin: 'Sys Admin',
  report_admin: 'Report Admin',
  rule_author: 'Rule Author',
  analyst: 'Analyst',
  viewer: 'Viewer',
};

/** Return a human-friendly display name for a role. */
function displayRoleName(role: string): string {
  return ROLE_DISPLAY_NAMES[role] ?? role;
}

/** Return a badge variant appropriate for the given role. */
function roleVariant(role: string): 'danger' | 'accent' | 'muted' {
  if (role === 'sys_admin') return 'danger';
  if (role === 'report_admin' || role === 'analyst' || role === 'rule_author') return 'accent';
  return 'muted';
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function roleLabel(roleName: string): { text: string; variant: 'danger' | 'accent' | 'muted' } {
  return { text: displayRoleName(roleName), variant: roleVariant(roleName) };
}

function sessionRoleVariant(role: string): 'danger' | 'accent' | 'muted' {
  return roleVariant(role);
}

function sessionRoleLabel(role: string): string {
  return displayRoleName(role);
}

function mfaVariant(mfaEnabled: boolean): 'success' | 'attention' {
  return mfaEnabled ? 'success' : 'attention';
}

function teamSlugFromAssignment(a: RoleAssignment): string {
  if (a.github_team_slug) return `@${a.github_team_slug}`;
  return `@${a.github_login}`;
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
  const [teamSlug, setTeamSlug] = useState('');
  const [role, setRole] = useState(roles[0] ?? 'viewer');

  const { data: syncedTeams } = useQuery({
    queryKey: ['synced-teams'],
    queryFn: listSyncedTeams,
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({
      github_login: login,
      role_name: role,
      scope_type: 'global',
      ...(teamSlug ? { github_team_slug: teamSlug } : {}),
    });
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
        <label className={styles.formLabel}>GitHub team (optional)</label>
        {syncedTeams && syncedTeams.length > 0 ? (
          <select
            className={styles.formSelect}
            value={teamSlug}
            onChange={(e) => setTeamSlug(e.target.value)}
          >
            <option value="">None (individual)</option>
            {syncedTeams.map((t) => (
              <option key={`${t.org}/${t.team_slug}`} value={t.team_slug}>
                {t.org}/{t.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            className={styles.formInput}
            value={teamSlug}
            onChange={(e) => setTeamSlug(e.target.value)}
            placeholder={syncedTeams ? 'No synced teams — type slug' : 'Loading teams…'}
          />
        )}
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Role</label>
        <select
          className={styles.formSelect}
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          {roles.map((r) => <option key={r} value={r}>{displayRoleName(r)}</option>)}
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
  const [login, setLogin] = useState(assignment.github_login);
  const [role, setRole] = useState(assignment.role_name ?? roles[0] ?? 'viewer');

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
          {roles.map((r) => <option key={r} value={r}>{displayRoleName(r)}</option>)}
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
/*  Team Mappings DataTable                                            */
/* ------------------------------------------------------------------ */

function TeamMappingsDataTable({
  assignments,
  navigate,
  setEditTarget,
  setDeleteTarget,
}: {
  assignments: readonly RoleAssignment[];
  navigate: ReturnType<typeof useNavigate>;
  setEditTarget: (a: RoleAssignment) => void;
  setDeleteTarget: (a: RoleAssignment) => void;
}) {
  const columns: ColumnDef<RoleAssignment>[] = useMemo(
    () => [
      {
        key: 'github_team',
        header: 'GitHub team',
        sortable: true,
        filterable: true,
        sortValue: (a) => teamSlugFromAssignment(a).toLowerCase(),
        filterValue: (a) => teamSlugFromAssignment(a),
        render: (a) => (
          <span className={styles.teamName}>{teamSlugFromAssignment(a)}</span>
        ),
      },
      {
        key: 'role',
        header: 'OctoWatch role',
        sortable: true,
        filterable: true,
        sortValue: (a) => {
          const rl = roleLabel(a.role_name);
          return rl.text.toLowerCase();
        },
        filterValue: (a) => roleLabel(a.role_name).text,
        render: (a) => {
          const rl = roleLabel(a.role_name);
          return <Label variant={rl.variant}>{rl.text}</Label>;
        },
      },
      {
        key: 'mapped_by',
        header: 'Mapped by',
        render: (a) => (
          <span
            className={`${styles.mention} ${styles.clickableMention}`}
            role="link"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/events?actor=${a.granted_by}`);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') navigate(`/events?actor=${a.granted_by}`);
            }}
          >
            @{a.granted_by}
          </span>
        ),
      },
      {
        key: 'last_synced',
        header: 'Last synced',
        sortable: true,
        sortValue: (a) => a.granted_at,
        render: (a) => (
          <span className={styles.muted}>{formatRelative(a.granted_at)}</span>
        ),
      },
      {
        key: 'actions',
        header: '',
        render: (a) => (
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <Button
              size="sm"
              onClick={(e: React.MouseEvent) => {
                e.stopPropagation();
                setEditTarget(a);
              }}
            >
              Edit
            </Button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(a);
              }}
              aria-label={`Remove mapping for ${a.github_login}`}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--fg-muted)',
                fontSize: 16,
                padding: '2px 6px',
                borderRadius: 4,
              }}
            >
              ×
            </button>
          </div>
        ),
      },
    ],
    [navigate, setEditTarget, setDeleteTarget],
  );

  return (
    <DataTable<RoleAssignment>
      columns={columns}
      data={assignments as RoleAssignment[]}
      rowKey={(a) => a.id}
      emptyMessage="No team mappings configured"
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Active Users DataTable                                             */
/* ------------------------------------------------------------------ */

function ActiveUsersDataTable({
  sessions,
  navigate,
  setSessionUser,
}: {
  sessions: readonly ActiveSession[];
  navigate: ReturnType<typeof useNavigate>;
  setSessionUser: (u: ActiveSession) => void;
}) {
  const columns: ColumnDef<ActiveSession>[] = useMemo(
    () => [
      {
        key: 'user',
        header: 'User',
        sortable: true,
        filterable: true,
        sortValue: (u) => u.login.toLowerCase(),
        filterValue: (u) => u.login,
        render: (u) => (
          <span
            className={`${styles.mention} ${styles.clickableMention}`}
            role="link"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/events?actor=${u.login}`);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') navigate(`/events?actor=${u.login}`);
            }}
          >
            @{u.login}
          </span>
        ),
      },
      {
        key: 'role',
        header: 'Role',
        sortable: true,
        filterable: true,
        sortValue: (u) => sessionRoleLabel(u.role).toLowerCase(),
        filterValue: (u) => sessionRoleLabel(u.role),
        render: (u) => (
          <Label variant={sessionRoleVariant(u.role)}>{sessionRoleLabel(u.role)}</Label>
        ),
      },
      {
        key: 'last_active',
        header: 'Last active',
        sortable: true,
        sortValue: (u) => u.last_active_at ?? '',
        render: (u) => (
          <span className={styles.muted}>
            {formatRelative(u.last_active_at)}
          </span>
        ),
      },
      {
        key: 'mfa',
        header: 'MFA',
        sortable: true,
        sortValue: (u) => (u.mfa_enabled ? 0 : 1),
        render: (u) => (
          <Label variant={mfaVariant(u.mfa_enabled)}>
            {u.mfa_enabled ? 'enabled' : 'pending'}
          </Label>
        ),
      },
      {
        key: 'sessions',
        header: 'Sessions',
        render: (u) => (
          <span
            className={styles.clickableSession}
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              setSessionUser(u);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setSessionUser(u);
            }}
          >
            {u.session_count}
          </span>
        ),
      },
    ],
    [navigate, setSessionUser],
  );

  return (
    <DataTable<ActiveSession>
      columns={columns}
      data={sessions as ActiveSession[]}
      rowKey={(u) => u.login}
      onRowClick={(u) => navigate(`/events?actor=${u.login}`)}
      emptyMessage="No active sessions"
    />
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
          <TeamMappingsDataTable
            assignments={assignments ?? []}
            navigate={navigate}
            setEditTarget={setEditTarget}
            setDeleteTarget={setDeleteTarget}
          />
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
          <ActiveUsersDataTable
            sessions={sessions ?? []}
            navigate={navigate}
            setSessionUser={setSessionUser}
          />
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
              <dd>{formatRelative(sessionUser.last_active_at)}</dd>
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
