import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PageHeader } from '../../components/common/PageHeader';
import { ErrorState } from '../../components/common/ErrorState';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { LoadingButton } from '../../components/common/LoadingButton';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../hooks/useToast';
import {
  listAuthMethods,
  updateAuthMethod,
  testSAMLConnection,
  listSessionPolicies,
  updateSessionPolicy,
} from '../../api/adminAuth';
import type {
  AuthMethodConfig,
  SessionPolicySetting,
} from '../../api/adminAuth';
import styles from './AuthSettings.module.css';

/* ──────────────── Method descriptions ──────────────── */
const METHOD_DESCRIPTIONS: Record<string, string> = {
  github_oauth: 'Sign in with GitHub OAuth. Requires a configured GitHub App.',
  saml_sso: 'Enterprise SAML single sign-on via your identity provider.',
  local_password: 'Username and password authentication (development only).',
};

/* ──────────────── Auth Method Card ──────────────── */
function MethodCard({
  method,
  onToggle,
  onConfigure,
}: {
  method: AuthMethodConfig;
  onToggle: (m: AuthMethodConfig) => void;
  onConfigure: (m: AuthMethodConfig) => void;
}) {
  return (
    <div className={styles.methodCard}>
      <div className={styles.methodHeader}>
        <span className={styles.methodName}>{method.display_name}</span>
        <span className={method.enabled ? styles.badgeEnabled : styles.badgeDisabled}>
          {method.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </div>
      <p className={styles.methodDescription}>
        {METHOD_DESCRIPTIONS[method.method_name] ?? 'Authentication method.'}
      </p>
      <div className={styles.methodActions}>
        <LoadingButton size="sm" variant="default" onClick={() => onToggle(method)}>
          {method.enabled ? 'Disable' : 'Enable'}
        </LoadingButton>
        {method.method_name === 'saml_sso' && (
          <LoadingButton size="sm" variant="primary" onClick={() => onConfigure(method)}>
            Configure
          </LoadingButton>
        )}
      </div>
    </div>
  );
}

/* ──────────────── SAML Config Form ──────────────── */
function SAMLConfigForm({
  method,
  onSaved,
}: {
  method: AuthMethodConfig;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const config = (method.config_json ?? {}) as Record<string, string>;
  const [idpEntityId, setIdpEntityId] = useState(config.idp_entity_id ?? '');
  const [idpSsoUrl, setIdpSsoUrl] = useState(config.idp_sso_url ?? '');
  const [idpCert, setIdpCert] = useState(config.idp_x509_cert ?? '');

  const save = useMutation({
    mutationFn: () =>
      updateAuthMethod('saml_sso', {
        config_json: { idp_entity_id: idpEntityId, idp_sso_url: idpSsoUrl, idp_x509_cert: idpCert },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'auth-methods'] });
      showToast('SAML configuration saved', 'success');
      onSaved();
    },
    onError: () => showToast('Failed to save SAML configuration', 'error'),
  });

  const testConn = useMutation({
    mutationFn: testSAMLConnection,
    onSuccess: (result) => {
      showToast(result.message, result.success ? 'success' : 'warning');
    },
    onError: () => showToast('Connection test failed', 'error'),
  });

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>SAML Configuration</h3>
      <p className={styles.sectionDescription}>
        Configure your Identity Provider (IdP) settings for SAML single sign-on.
      </p>
      <div className={styles.formGrid}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="idp-entity-id">IdP Entity ID</label>
          <input
            id="idp-entity-id"
            className={styles.input}
            value={idpEntityId}
            onChange={(e) => setIdpEntityId(e.target.value)}
            placeholder="https://idp.example.com/entity"
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="idp-sso-url">IdP SSO URL</label>
          <input
            id="idp-sso-url"
            className={styles.input}
            value={idpSsoUrl}
            onChange={(e) => setIdpSsoUrl(e.target.value)}
            placeholder="https://idp.example.com/sso"
          />
        </div>
        <div className={styles.fieldFull}>
          <label className={styles.label} htmlFor="idp-cert">IdP X.509 Certificate</label>
          <textarea
            id="idp-cert"
            className={styles.input}
            value={idpCert}
            onChange={(e) => setIdpCert(e.target.value)}
            placeholder="-----BEGIN CERTIFICATE-----"
            rows={4}
            style={{ resize: 'vertical' }}
          />
        </div>
        <div className={styles.formActions}>
          <LoadingButton
            size="sm"
            variant="default"
            loading={testConn.isPending}
            onClick={() => testConn.mutate()}
          >
            Test Connection
          </LoadingButton>
          <LoadingButton
            size="sm"
            variant="primary"
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            Save Configuration
          </LoadingButton>
        </div>
      </div>
    </div>
  );
}

/* ──────────────── Session Policy Panel ──────────────── */
function SessionPolicyPanel() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const { data: policies, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin', 'session-policies'],
    queryFn: listSessionPolicies,
  });

  const initialEdits = useMemo(() => {
    if (!policies) return {};
    const initial: Record<string, string> = {};
    for (const p of policies) {
      initial[p.policy_key] = p.policy_value;
    }
    return initial;
  }, [policies]);

  const [edits, setEdits] = useState<Record<string, string>>({});
  const mergedEdits = { ...initialEdits, ...edits };

  const saveMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      updateSessionPolicy(key, { policy_value: value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'session-policies'] });
      showToast('Session policy updated', 'success');
    },
    onError: () => showToast('Failed to update session policy', 'error'),
  });

  if (isLoading) return <SkeletonCard lines={4} />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>Session Policies</h3>
      <p className={styles.sectionDescription}>
        Configure session duration, idle timeouts, and other session-related policies.
      </p>
      <table className={styles.policyTable}>
        <thead>
          <tr>
            <th>Policy</th>
            <th>Value</th>
            <th>Description</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {policies?.map((p: SessionPolicySetting) => (
            <tr key={p.policy_key}>
              <td>{p.policy_key}</td>
              <td>
                <input
                  className={styles.policyInput}
                  value={mergedEdits[p.policy_key] ?? p.policy_value}
                  onChange={(e) =>
                    setEdits((prev) => ({ ...prev, [p.policy_key]: e.target.value }))
                  }
                />
              </td>
              <td style={{ color: 'var(--fg-muted)', fontSize: 12 }}>{p.description}</td>
              <td>
                <LoadingButton
                  size="sm"
                  variant="primary"
                  loading={saveMutation.isPending}
                  disabled={mergedEdits[p.policy_key] === p.policy_value}
                  onClick={() =>
                    saveMutation.mutate({
                      key: p.policy_key,
                      value: mergedEdits[p.policy_key] ?? p.policy_value,
                    })
                  }
                >
                  Save
                </LoadingButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ──────────────── Main Page ──────────────── */
export default function AuthSettingsPage() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [configuringMethod, setConfiguringMethod] = useState<AuthMethodConfig | null>(null);
  const [confirmToggle, setConfirmToggle] = useState<AuthMethodConfig | null>(null);

  const {
    data: methods,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['admin', 'auth-methods'],
    queryFn: listAuthMethods,
  });

  const toggleMutation = useMutation({
    mutationFn: (m: AuthMethodConfig) =>
      updateAuthMethod(m.method_name, { enabled: !m.enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'auth-methods'] });
      showToast('Auth method updated', 'success');
      setConfirmToggle(null);
    },
    onError: () => {
      showToast('Failed to update auth method', 'error');
      setConfirmToggle(null);
    },
  });

  return (
    <div className={styles.page}>
      <PageHeader
        title="Authentication Settings"
        description="Manage sign-in methods, SAML SSO, and session policies."
        breadcrumbs={[
          { label: 'Admin', href: '/admin' },
          { label: 'Authentication' },
        ]}
      />

      {/* Auth Methods */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Authentication Methods</h3>
        <p className={styles.sectionDescription}>
          Enable or disable sign-in methods for your organization.
        </p>

        {isLoading && (
          <div className={styles.methodGrid}>
            <SkeletonCard lines={3} />
            <SkeletonCard lines={3} />
            <SkeletonCard lines={3} />
          </div>
        )}

        {isError && <ErrorState onRetry={() => refetch()} />}

        {methods && (
          <div className={styles.methodGrid}>
            {methods.map((m: AuthMethodConfig) => (
              <MethodCard
                key={m.method_name}
                method={m}
                onToggle={(method) => setConfirmToggle(method)}
                onConfigure={(method) => setConfiguringMethod(method)}
              />
            ))}
          </div>
        )}
      </div>

      {/* SAML Configuration */}
      {configuringMethod?.method_name === 'saml_sso' && (
        <SAMLConfigForm
          method={configuringMethod}
          onSaved={() => setConfiguringMethod(null)}
        />
      )}

      {/* Session Policies */}
      <SessionPolicyPanel />

      {/* Confirm Toggle Dialog */}
      <ConfirmDialog
        open={!!confirmToggle}
        title={confirmToggle?.enabled ? 'Disable Auth Method' : 'Enable Auth Method'}
        message={
          confirmToggle?.enabled
            ? `Are you sure you want to disable ${confirmToggle.display_name}? Users will no longer be able to sign in with this method.`
            : `Enable ${confirmToggle?.display_name} as a sign-in method?`
        }
        confirmLabel={confirmToggle?.enabled ? 'Disable' : 'Enable'}
        confirmVariant={confirmToggle?.enabled ? 'danger' : 'primary'}
        onConfirm={() => confirmToggle && toggleMutation.mutate(confirmToggle)}
        onCancel={() => setConfirmToggle(null)}
        loading={toggleMutation.isPending}
      />
    </div>
  );
}
