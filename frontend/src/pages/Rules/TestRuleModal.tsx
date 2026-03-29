import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { testRule } from '../../api/rules';
import type { RuleTestEventResponse } from '../../api/rules';
import type { RuleResponse, RuleCategory } from '../../types/detections';
import { Modal } from '../../components/primitives/Modal';
import { Button } from '../../components/primitives/Button';
import styles from './Rules.module.css';

/** Generate a plausible sample event for a given rule category. */
function getSampleEvent(category: RuleCategory): Record<string, unknown> {
  const base = {
    actor: 'octocat',
    actor_id: 583231,
    org: 'my-org',
    created_at: new Date().toISOString(),
  };

  switch (category) {
    case 'exfiltration':
      return { ...base, action: 'repo.clone', repo: 'my-org/private-repo', source_ip: '203.0.113.42', data: { transport_protocol_name: 'http', visibility: 'private' } };
    case 'account_compromise':
      return { ...base, action: 'auth.login', source_ip: '198.51.100.1', data: { auth_method: 'password' } };
    case 'privilege_escalation':
      return { ...base, action: 'org.update_member', repo: 'my-org/admin-repo', data: { permission: 'admin', old_permission: 'read' } };
    case 'secret_leakage':
      return { ...base, action: 'git.push', repo: 'my-org/app-repo', data: { alert_type: 'secret_scanning' } };
    case 'supply_chain':
      return { ...base, action: 'packages.package_version_published', repo: 'my-org/npm-pkg', data: { package_type: 'npm' } };
    case 'branch_protection_bypass':
      return { ...base, action: 'protected_branch.policy_override', repo: 'my-org/main-repo', data: { branch: 'main' } };
    case 'pat_abuse':
      return { ...base, action: 'personal_access_token.create', data: { scopes: 'repo,admin:org' } };
    case 'impossible_travel':
      return { ...base, action: 'auth.login', source_ip: '203.0.113.42', geo_country_code: 'US', geo_latitude: 37.7749, geo_longitude: -122.4194, data: {} };
    case 'off_hours_anomaly':
      return { ...base, action: 'repos.create', repo: 'my-org/new-repo', data: {} };
    default:
      return { ...base, action: 'repos.create', repo: 'my-org/hello-world', data: { description: 'A new repository' } };
  }
}

interface TestRuleModalProps {
  readonly rule: RuleResponse | null;
  readonly onClose: () => void;
}

export function TestRuleModal({ rule, onClose }: TestRuleModalProps) {
  const [eventJson, setEventJson] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [result, setResult] = useState<RuleTestEventResponse | null>(null);

  const initializeJson = useCallback((r: RuleResponse) => {
    const sample = getSampleEvent(r.category);
    setEventJson(JSON.stringify(sample, null, 2));
    setParseError(null);
    setResult(null);
  }, []);

  // Reset state when the modal opens with a new rule
  const prevRuleRef = useState<number | null>(null);
  if (rule && prevRuleRef[0] !== rule.id) {
    prevRuleRef[1](rule.id);
    initializeJson(rule);
  }

  const mutation = useMutation({
    mutationFn: (event: Record<string, unknown>) => testRule(rule!.id, event),
    onSuccess: (data) => {
      setResult(data);
      setParseError(null);
    },
    onError: (err: Error) => {
      setParseError(`API error: ${err.message}`);
    },
  });

  function handleRunTest() {
    setParseError(null);
    setResult(null);

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(eventJson) as Record<string, unknown>;
    } catch {
      setParseError('Invalid JSON. Please check syntax.');
      return;
    }

    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      setParseError('Event must be a JSON object.');
      return;
    }

    mutation.mutate(parsed);
  }

  function handleClose() {
    setResult(null);
    setParseError(null);
    onClose();
  }

  return (
    <Modal open={!!rule} onClose={handleClose} title={`Test Rule: ${rule?.name ?? ''}`} width={640}>
      <div className={styles.testModalContent}>
        <div className={styles.formRow}>
          <label className={styles.formLabel} htmlFor="test-event-json">
            Sample event payload (JSON)
          </label>
          <textarea
            id="test-event-json"
            className={styles.testJsonEditor}
            value={eventJson}
            onChange={(e) => {
              setEventJson(e.target.value);
              setParseError(null);
            }}
            rows={14}
            spellCheck={false}
          />
        </div>

        {parseError && (
          <div className={styles.testError} role="alert">
            {parseError}
          </div>
        )}

        {result && (
          <div
            className={result.matched ? styles.testResultMatch : styles.testResultNoMatch}
            role="status"
            data-testid="test-result"
          >
            <div className={styles.testResultHeading}>
              {result.matched ? '✓ Rule would trigger' : '✗ Rule would not trigger'}
            </div>
            <div className={styles.testResultReason}>{result.reason}</div>
            {result.matched && result.matched_fields.length > 0 && (
              <div className={styles.testMatchedFields}>
                <span className={styles.testMatchedFieldsLabel}>Matched fields:</span>
                <ul className={styles.testMatchedFieldsList}>
                  {result.matched_fields.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className={styles.formActions}>
          <Button variant="default" onClick={handleClose} type="button">
            Close
          </Button>
          <Button
            variant="primary"
            onClick={handleRunTest}
            type="button"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Testing…' : 'Run Test'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
