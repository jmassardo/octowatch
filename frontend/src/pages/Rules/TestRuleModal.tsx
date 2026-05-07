import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { testRule } from '../../api/rules';
import type { RuleTestEventResponse } from '../../api/rules';
import type { RuleResponse } from '../../types/detections';
import { Drawer } from '../../components/primitives/Drawer';
import { Button } from '../../components/primitives/Button';
import { getSampleEvent } from './sampleEvent';
import styles from './Rules.module.css';

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
    <Drawer open={!!rule} onClose={handleClose} title={`Test Rule: ${rule?.name ?? ''}`}>
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
    </Drawer>
  );
}
