import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPlaybookExecution,
  getPlaybookTemplate,
  completePlaybookStep,
  skipPlaybookStep,
  completePlaybookExecution,
} from '../../api/playbooks';
import type { PlaybookStepResult } from '../../api/playbooks';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Label } from '../../components/primitives/Label';
import { formatRelativeShort } from '../../utils/dates';
import styles from './Playbooks.module.css';

interface PlaybookRunnerProps {
  /** The execution ID to display. */
  executionId: number;
  /** Called when navigating away from the runner. */
  onBack: () => void;
}

/**
 * PlaybookRunner — Step-by-step guided workflow for executing a playbook.
 *
 * Displays each step with its instructions, allows completing or skipping
 * steps, shows a progress bar, and provides a side panel with context.
 */
export function PlaybookRunner({ executionId, onBack }: PlaybookRunnerProps) {
  const queryClient = useQueryClient();
  const [notesMap, setNotesMap] = useState<Record<number, string>>({});
  const [skipReasonMap, setSkipReasonMap] = useState<Record<number, string>>({});
  const [showSkipFor, setShowSkipFor] = useState<number | null>(null);

  const {
    data: execution,
    isLoading: execLoading,
    error: execError,
  } = useQuery({
    queryKey: ['playbook-execution', executionId],
    queryFn: () => getPlaybookExecution(executionId),
    refetchInterval: 5000,
  });

  const { data: template } = useQuery({
    queryKey: ['playbook-template', execution?.template_id],
    queryFn: () => getPlaybookTemplate(execution!.template_id),
    enabled: !!execution?.template_id,
  });

  const completeMutation = useMutation({
    mutationFn: ({ stepIndex, notes }: { stepIndex: number; notes: string }) =>
      completePlaybookStep(executionId, stepIndex, { completed: true, notes }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['playbook-execution', executionId] });
    },
  });

  const skipMutation = useMutation({
    mutationFn: ({ stepIndex, reason }: { stepIndex: number; reason: string }) =>
      skipPlaybookStep(executionId, stepIndex, { reason }),
    onSuccess: () => {
      setShowSkipFor(null);
      void queryClient.invalidateQueries({ queryKey: ['playbook-execution', executionId] });
    },
  });

  const finishMutation = useMutation({
    mutationFn: () => completePlaybookExecution(executionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['playbook-execution', executionId] });
      void queryClient.invalidateQueries({ queryKey: ['playbook-executions'] });
    },
  });

  if (execLoading) {
    return (
      <div className={styles.page}>
        <Spinner />
      </div>
    );
  }

  if (execError || !execution) {
    return (
      <div className={styles.page}>
        <ErrorBanner message="Failed to load playbook execution." />
        <Button onClick={onBack}>← Back</Button>
      </div>
    );
  }

  const steps: PlaybookStepResult[] = execution.step_results;
  const completedCount = steps.filter((s) => s.completed).length;
  const totalSteps = steps.length;
  const progressPct = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;
  const isCompleted = execution.status === 'completed' || execution.status === 'cancelled';
  const allStepsDone = completedCount === totalSteps;

  // Find current (first incomplete) step
  const currentStepIndex = steps.findIndex((s) => !s.completed);

  // Get template step details for enriched display
  const templateSteps = template?.steps ?? [];

  function getStepBadge(step: PlaybookStepResult, idx: number) {
    if (step.skipped) {
      return <span className={`${styles.stepBadge} ${styles.stepBadgeSkipped}`}>Skipped</span>;
    }
    if (step.completed) {
      return <span className={`${styles.stepBadge} ${styles.stepBadgeCompleted}`}>Completed</span>;
    }
    if (idx === currentStepIndex) {
      return <span className={`${styles.stepBadge} ${styles.stepBadgeActive}`}>Current</span>;
    }
    return <span className={styles.stepBadge}>Pending</span>;
  }

  return (
    <div className={styles.page}>
      <Button size="sm" onClick={onBack}>
        ← Back to Playbooks
      </Button>

      <h2>{template?.name ?? 'Playbook Execution'}</h2>

      {/* Progress bar */}
      <div className={styles.progressBar}>
        <div className={styles.progressFill} style={{ width: `${progressPct}%` }} />
      </div>
      <p className={styles.progressText}>
        {completedCount} of {totalSteps} steps completed ({progressPct}%)
      </p>

      <div className={styles.runner}>
        {/* Main step area */}
        <div className={styles.runnerMain}>
          {steps.map((step, idx) => {
            const templateStep = templateSteps[idx];
            const isActive = idx === currentStepIndex && !isCompleted;
            const cardClass = [
              styles.stepCard,
              isActive && styles.stepCardActive,
              step.completed && styles.stepCardCompleted,
            ]
              .filter(Boolean)
              .join(' ');

            return (
              <div key={idx} className={cardClass} data-testid={`step-${idx}`}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <h3 className={styles.stepTitle}>
                    Step {idx + 1}: {step.title}
                  </h3>
                  {getStepBadge(step, idx)}
                </div>

                {templateStep && <p className={styles.stepDesc}>{templateStep.description}</p>}

                {templateStep?.action_type && (
                  <Label variant="muted">{templateStep.action_type}</Label>
                )}

                {step.skipped && step.skip_reason && (
                  <p className={styles.stepDesc}>
                    <strong>Skip reason:</strong> {step.skip_reason}
                  </p>
                )}

                {step.completed && step.notes && (
                  <p className={styles.stepDesc}>
                    <strong>Notes:</strong> {step.notes}
                  </p>
                )}

                {isActive && !step.completed && (
                  <>
                    <textarea
                      className={styles.notesInput}
                      placeholder="Notes (optional)…"
                      value={notesMap[idx] ?? ''}
                      onChange={(e) => setNotesMap((m) => ({ ...m, [idx]: e.target.value }))}
                      rows={2}
                    />
                    <div className={styles.stepActions}>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() =>
                          completeMutation.mutate({
                            stepIndex: idx,
                            notes: notesMap[idx] ?? '',
                          })
                        }
                        disabled={completeMutation.isPending}
                      >
                        {completeMutation.isPending ? 'Completing…' : 'Complete Step'}
                      </Button>

                      {showSkipFor === idx ? (
                        <>
                          <input
                            className={styles.skipInput}
                            placeholder="Reason for skipping…"
                            value={skipReasonMap[idx] ?? ''}
                            onChange={(e) =>
                              setSkipReasonMap((m) => ({ ...m, [idx]: e.target.value }))
                            }
                          />
                          <Button
                            size="sm"
                            onClick={() =>
                              skipMutation.mutate({
                                stepIndex: idx,
                                reason: skipReasonMap[idx] ?? '',
                              })
                            }
                            disabled={skipMutation.isPending || !(skipReasonMap[idx] ?? '').trim()}
                          >
                            Confirm Skip
                          </Button>
                          <Button size="sm" onClick={() => setShowSkipFor(null)}>
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <Button size="sm" onClick={() => setShowSkipFor(idx)}>
                          Skip Step
                        </Button>
                      )}
                    </div>
                  </>
                )}
              </div>
            );
          })}

          {/* Complete execution button */}
          {allStepsDone && !isCompleted && (
            <Button
              variant="primary"
              onClick={() => finishMutation.mutate()}
              disabled={finishMutation.isPending}
            >
              {finishMutation.isPending ? 'Completing…' : 'Complete Playbook & Resolve Detection'}
            </Button>
          )}

          {isCompleted && <Label variant="success">Playbook execution completed</Label>}
        </div>

        {/* Side panel — detection context */}
        <div className={styles.runnerSide}>
          <h3>Execution Details</h3>

          <div className={styles.sideSection}>
            <div className={styles.sideLabel}>Status</div>
            <div className={styles.sideValue}>
              <Label
                variant={
                  execution.status === 'completed'
                    ? 'success'
                    : execution.status === 'in_progress'
                      ? 'attention'
                      : 'muted'
                }
              >
                {execution.status}
              </Label>
            </div>
          </div>

          <div className={styles.sideSection}>
            <div className={styles.sideLabel}>Detection ID</div>
            <div className={styles.sideValue}>#{execution.detection_id}</div>
          </div>

          <div className={styles.sideSection}>
            <div className={styles.sideLabel}>Started By</div>
            <div className={styles.sideValue}>{execution.started_by}</div>
          </div>

          <div className={styles.sideSection}>
            <div className={styles.sideLabel}>Started</div>
            <div className={styles.sideValue}>{formatRelativeShort(execution.started_at)}</div>
          </div>

          {execution.completed_at && (
            <div className={styles.sideSection}>
              <div className={styles.sideLabel}>Completed</div>
              <div className={styles.sideValue}>{formatRelativeShort(execution.completed_at)}</div>
            </div>
          )}

          {template && (
            <div className={styles.sideSection}>
              <div className={styles.sideLabel}>Categories</div>
              <div className={styles.sideValue}>
                {template.detection_categories.length > 0
                  ? template.detection_categories.join(', ')
                  : '—'}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
