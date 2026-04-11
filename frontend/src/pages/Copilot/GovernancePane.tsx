import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listCopilotPolicies,
  listCopilotViolations,
  updateCopilotPolicy,
} from '../../api/copilotGovernance';
import type { CopilotPolicy, CopilotPolicyViolation } from '../../api/copilotGovernance';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { formatRelativeShort } from '../../utils/dates';
import styles from './Copilot.module.css';

function PolicyCard({
  policy,
  onToggle,
}: {
  policy: CopilotPolicy;
  onToggle: (id: number, enabled: boolean) => void;
}) {
  return (
    <div className={styles.govCard}>
      <div className={styles.govCardHeader}>
        <span className={styles.govPolicyName}>{policy.name}</span>
        <Label variant={policy.enabled ? 'success' : 'muted'}>
          {policy.enabled ? 'Active' : 'Disabled'}
        </Label>
      </div>
      <div className={styles.govCardMeta}>
        <span>Type: {policy.policy_type}</span>
        <span>
          Severity: <Label variant={policy.severity === 'critical' ? 'danger' : 'muted'}>{policy.severity}</Label>
        </span>
      </div>
      <div className={styles.govCardActions}>
        <Button size="sm" onClick={() => onToggle(policy.id, !policy.enabled)}>
          {policy.enabled ? 'Disable' : 'Enable'}
        </Button>
      </div>
    </div>
  );
}

function ViolationRow({ violation }: { violation: CopilotPolicyViolation }) {
  return (
    <tr className={styles.govViolationRow}>
      <td>{violation.policy_name}</td>
      <td>
        <Label variant={violation.severity === 'critical' ? 'danger' : 'muted'}>
          {violation.severity}
        </Label>
      </td>
      <td>{violation.actor ?? '—'}</td>
      <td>{violation.org ?? '—'}</td>
      <td>{violation.description}</td>
      <td>
        <Label variant={violation.status === 'open' ? 'attention' : 'muted'}>
          {violation.status}
        </Label>
      </td>
      <td className={styles.govViolationTime}>{formatRelativeShort(violation.detected_at)}</td>
    </tr>
  );
}

export function GovernancePane() {
  const queryClient = useQueryClient();
  const [sevFilter, setSevFilter] = useState('');

  const {
    data: policies,
    isLoading: loadingPolicies,
    isError: policyError,
    refetch: refetchPolicies,
  } = useQuery({
    queryKey: ['copilot-governance', 'policies'],
    queryFn: listCopilotPolicies,
  });

  const {
    data: violationData,
    isLoading: loadingViolations,
    isError: violationError,
    refetch: refetchViolations,
  } = useQuery({
    queryKey: ['copilot-governance', 'violations', sevFilter],
    queryFn: () =>
      listCopilotViolations({
        severity: sevFilter || undefined,
        page_size: 50,
      }),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateCopilotPolicy(id, { enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['copilot-governance'] });
    },
  });

  const handleToggle = (id: number, enabled: boolean) => {
    toggleMutation.mutate({ id, enabled });
  };

  return (
    <div className={styles.govPane}>
      <div className={styles.govSection}>
        <div className={styles.govSectionTitle}>Governance Policies</div>
        {loadingPolicies && <Spinner />}
        {policyError && (
          <ErrorBanner message="Failed to load policies" onRetry={() => void refetchPolicies()} />
        )}
        {policies && policies.length === 0 && (
          <div className={styles.govEmpty}>No governance policies configured</div>
        )}
        {policies && policies.length > 0 && (
          <div className={styles.govGrid}>
            {policies.map((p) => (
              <PolicyCard key={p.id} policy={p} onToggle={handleToggle} />
            ))}
          </div>
        )}
      </div>

      <div className={styles.govSection}>
        <div className={styles.govSectionTitle}>
          Policy Violations
          {violationData && <span className={styles.govCount}> ({violationData.total})</span>}
        </div>

        <div className={styles.govFilters}>
          <select
            className={styles.govSelect}
            value={sevFilter}
            onChange={(e) => setSevFilter(e.target.value)}
          >
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        {loadingViolations && <Spinner />}
        {violationError && (
          <ErrorBanner message="Failed to load violations" onRetry={() => void refetchViolations()} />
        )}
        {violationData && violationData.violations.length === 0 && (
          <div className={styles.govEmpty}>No violations found</div>
        )}
        {violationData && violationData.violations.length > 0 && (
          <table className={styles.govTable}>
            <thead>
              <tr>
                <th>Policy</th>
                <th>Severity</th>
                <th>Actor</th>
                <th>Org</th>
                <th>Description</th>
                <th>Status</th>
                <th>Detected</th>
              </tr>
            </thead>
            <tbody>
              {violationData.violations.map((v) => (
                <ViolationRow key={v.id} violation={v} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
