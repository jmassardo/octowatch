import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { updateDetectionStatus, deleteDetection, assignDetection } from '../../api/detections';
import { getDetectionTimeline } from '../../api/executive';
import { listPlaybookTemplates, executePlaybook } from '../../api/playbooks';
import type { TimelineEvent } from '../../api/executive';
import type { DetectionResponse } from '../../types/detections';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Autocomplete } from '../../components/primitives/Autocomplete';
import { formatRelativeShort, formatCompact } from '../../utils/dates';
import styles from './Threats.module.css';

/**
 * Safely convert any value to a display string.
 */
function safeText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

/**
 * Safely check whether an object has entries.
 */
function hasEntries(value: unknown): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    Object.keys(value).length > 0
  );
}

type DismissReason = 'False positive' | 'Expected behavior' | 'Duplicate' | "Won't fix";
const DISMISS_REASONS: DismissReason[] = [
  'False positive',
  'Expected behavior',
  'Duplicate',
  "Won't fix",
];

/* -------------------------------------------------------------------------- */
/*  Evidence display (moved from index.tsx)                                     */
/* -------------------------------------------------------------------------- */

function EvidenceValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  const [expanded, setExpanded] = useState(false);

  if (value === null || value === undefined) {
    return <span className={styles.evidenceMuted}>—</span>;
  }
  if (typeof value === 'string') {
    return <span className={styles.evidenceVal}>{value}</span>;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span className={styles.evidenceVal}>{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className={styles.evidenceMuted}>[]</span>;
    }
    const allPrimitive = value.every(
      (v) => typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean',
    );
    if (allPrimitive && value.length <= 5) {
      return <span className={styles.evidenceVal}>{value.join(', ')}</span>;
    }
    return (
      <div>
        <button
          type="button"
          className={styles.expandToggle}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '▾' : '▸'} {value.length} item{value.length !== 1 ? 's' : ''}
        </button>
        {expanded && (
          <div className={styles.evidenceNested}>
            {value.map((item, i) => (
              <div key={i} className={styles.evidenceRow}>
                <span className={styles.evidenceKey}>[{i}]</span>
                <EvidenceValue value={item} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className={styles.evidenceMuted}>{'{}'}</span>;
    }
    return (
      <div>
        <button
          type="button"
          className={styles.expandToggle}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '▾' : '▸'} {entries.length} field{entries.length !== 1 ? 's' : ''}
        </button>
        {expanded && (
          <div className={styles.evidenceNested}>
            {entries.map(([k, v]) => (
              <div key={k} className={styles.evidenceRow}>
                <span className={styles.evidenceKey}>{k}</span>
                <EvidenceValue value={v} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  return <span className={styles.evidenceVal}>{String(value)}</span>;
}

function EvidenceDisplay({ data }: { data: Record<string, unknown> }) {
  return (
    <div className={styles.evidenceTable}>
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className={styles.evidenceRow}>
          <span className={styles.evidenceKey}>{key}</span>
          <div className={styles.evidenceValWrap}>
            <EvidenceValue value={value} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Props                                                                       */
/* -------------------------------------------------------------------------- */

interface DetectionDetailPaneProps {
  selected: DetectionResponse;
  actorSuggestions: string[];
  onClose: () => void;
  onDeleted: () => void;
}

/* -------------------------------------------------------------------------- */
/*  Component                                                                   */
/* -------------------------------------------------------------------------- */

export function DetectionDetailPane({
  selected,
  actorSuggestions,
  onClose,
  onDeleted,
}: DetectionDetailPaneProps) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  // Local UI state
  const [showAssignDropdown, setShowAssignDropdown] = useState(false);
  const [assignValue, setAssignValue] = useState('');
  const [showDismissForm, setShowDismissForm] = useState(false);
  const [dismissReason, setDismissReason] = useState<DismissReason>('False positive');
  const [dismissNote, setDismissNote] = useState('');
  const [showResolveForm, setShowResolveForm] = useState(false);
  const [resolveNote, setResolveNote] = useState('');
  const [timelineExpanded, setTimelineExpanded] = useState(false);
  const [showPlaybooks, setShowPlaybooks] = useState(false);

  // Playbook templates query — lazy loaded when panel opens
  const { data: playbookTemplates } = useQuery({
    queryKey: ['playbook-templates'],
    queryFn: () => listPlaybookTemplates(),
    enabled: showPlaybooks,
    staleTime: 60_000,
  });

  // Filter templates by detection category if available
  const detectionCategory = selected.context_data?.category as string | undefined;
  const relevantPlaybooks = (playbookTemplates ?? []).filter((t) => {
    if (t.detection_categories.length === 0) return true;
    if (!detectionCategory) return true;
    return t.detection_categories.includes(detectionCategory);
  });

  const executePlaybookMutation = useMutation({
    mutationFn: (templateId: number) =>
      executePlaybook({ template_id: templateId, detection_id: selected.id }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['detections'] });
      navigate('/playbooks');
    },
  });

  // Mutations
  const assignMutation = useMutation({
    mutationFn: ({ id, assignee }: { id: number; assignee: string }) =>
      assignDetection(id, { assigned_to: assignee }),
    onSuccess: () => {
      setShowAssignDropdown(false);
      setAssignValue('');
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
  });

  const dismissMutation = useMutation({
    mutationFn: ({ id, note }: { id: number; note: string }) =>
      updateDetectionStatus(id, { status: 'false_positive', resolution_note: note }),
    onSuccess: () => {
      setShowDismissForm(false);
      setDismissReason('False positive');
      setDismissNote('');
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: ({ id, note }: { id: number; note: string }) =>
      updateDetectionStatus(id, {
        status: 'resolved',
        resolution_note: note || undefined,
      }),
    onSuccess: () => {
      setShowResolveForm(false);
      setResolveNote('');
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
  });

  const reopenMutation = useMutation({
    mutationFn: (id: number) => updateDetectionStatus(id, { status: 'open' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteDetection(id),
    onSuccess: () => {
      onDeleted();
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
  });

  // Timeline query (lazy — only fetched when expanded)
  const {
    data: timelineData,
    isLoading: timelineLoading,
    isError: timelineError,
    refetch: refetchTimeline,
  } = useQuery({
    queryKey: ['detection-timeline', selected.id],
    queryFn: () => getDetectionTimeline(selected.id),
    enabled: timelineExpanded,
    staleTime: 30_000,
  });

  const timelineEvents: readonly TimelineEvent[] = timelineData?.events ?? [];

  const sevLabelVariant = (sev: string) => {
    if (sev === 'critical') return 'danger' as const;
    if (sev === 'high') return 'severe' as const;
    if (sev === 'medium') return 'attention' as const;
    return 'success' as const;
  };

  const statusColor = (status: string) => {
    if (status === 'open') return 'danger' as const;
    if (status === 'investigating') return 'attention' as const;
    if (status === 'resolved') return 'success' as const;
    return 'muted' as const;
  };

  const isActionable = selected.status === 'open' || selected.status === 'investigating';
  const isResolvable = selected.status === 'investigating';
  const isReopenable = selected.status === 'resolved' || selected.status === 'false_positive';

  const eventIds = Array.isArray(selected.event_ids) ? selected.event_ids : [];

  return (
    <>
      {/* Header */}
      <div className={styles.panelHeader}>
        <div style={{ fontWeight: 600 }}>{safeText(selected.title)}</div>
        <button className={styles.panelClose} onClick={onClose}>
          &#215;
        </button>
      </div>

      {/* Labels row */}
      <div className={styles.panelLabels}>
        <Label variant={sevLabelVariant(selected.severity)}>{selected.severity}</Label>
        <Label variant={statusColor(selected.status)}>{selected.status.replace('_', ' ')}</Label>
        {selected.rule_name && <Label variant="muted">{safeText(selected.rule_name)}</Label>}
        {selected.confidence_score > 0 && (
          <span className={styles.confidenceBadge}>
            {Math.round(selected.confidence_score * 100)}% confidence
          </span>
        )}
        {selected.is_dry_run && <Label variant="attention">Dry Run</Label>}
      </div>

      {/* Primary Actions — prominent placement */}
      <div className={styles.panelActions}>
        {isActionable && (
          <>
            <Button
              size="sm"
              variant="primary"
              onClick={() => setShowAssignDropdown((v) => !v)}
              disabled={assignMutation.isPending}
            >
              👤 Assign
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={() => setShowDismissForm((v) => !v)}
              disabled={dismissMutation.isPending}
            >
              ✕ Dismiss
            </Button>
          </>
        )}
        {isResolvable && (
          <Button
            size="sm"
            onClick={() => setShowResolveForm((v) => !v)}
            disabled={resolveMutation.isPending}
          >
            ✓ Resolve
          </Button>
        )}
        {isReopenable && (
          <Button
            size="sm"
            onClick={() => reopenMutation.mutate(selected.id)}
            disabled={reopenMutation.isPending}
          >
            {reopenMutation.isPending ? 'Reopening…' : '↺ Reopen'}
          </Button>
        )}
        <Button size="sm" variant="primary" onClick={() => setShowPlaybooks((v) => !v)}>
          ▶ Run Playbook
        </Button>
      </div>

      {/* Assign Dropdown */}
      {showAssignDropdown && (
        <div className={styles.assignDropdown} data-testid="assign-dropdown">
          <Autocomplete
            value={assignValue}
            onChange={setAssignValue}
            suggestions={actorSuggestions}
            placeholder="Enter username…"
            ariaLabel="Assign to username"
            className={styles.filterInput}
          />
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              if (assignValue.trim()) {
                assignMutation.mutate({ id: selected.id, assignee: assignValue.trim() });
              }
            }}
            disabled={!assignValue.trim() || assignMutation.isPending}
          >
            {assignMutation.isPending ? 'Assigning…' : 'Confirm Assign'}
          </Button>
        </div>
      )}

      {/* Dismiss Form */}
      {showDismissForm && (
        <div className={styles.dismissForm} data-testid="dismiss-form">
          <fieldset className={styles.dismissReasons}>
            <legend className={styles.dismissLegend}>Reason for dismissal</legend>
            {DISMISS_REASONS.map((reason) => (
              <label key={reason} className={styles.dismissRadio}>
                <input
                  type="radio"
                  name="dismiss-reason"
                  value={reason}
                  checked={dismissReason === reason}
                  onChange={() => setDismissReason(reason)}
                />
                {reason}
              </label>
            ))}
          </fieldset>
          <textarea
            className={styles.dismissTextarea}
            placeholder="Additional notes (optional)…"
            value={dismissNote}
            onChange={(e) => setDismissNote(e.target.value)}
            rows={2}
          />
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              const note = dismissNote.trim()
                ? `${dismissReason}: ${dismissNote.trim()}`
                : dismissReason;
              dismissMutation.mutate({ id: selected.id, note });
            }}
            disabled={dismissMutation.isPending}
          >
            {dismissMutation.isPending ? 'Dismissing…' : 'Confirm Dismiss'}
          </Button>
        </div>
      )}

      {/* Resolve Form */}
      {showResolveForm && (
        <div className={styles.dismissForm} data-testid="resolve-form">
          <textarea
            className={styles.dismissTextarea}
            placeholder="Resolution notes (optional)…"
            value={resolveNote}
            onChange={(e) => setResolveNote(e.target.value)}
            rows={2}
          />
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              resolveMutation.mutate({ id: selected.id, note: resolveNote.trim() });
            }}
            disabled={resolveMutation.isPending}
          >
            {resolveMutation.isPending ? 'Resolving…' : 'Confirm Resolve'}
          </Button>
        </div>
      )}

      {/* Playbook selection panel */}
      {showPlaybooks && (
        <div className={styles.dismissForm} data-testid="playbook-panel">
          <strong>Select a playbook to run:</strong>
          {relevantPlaybooks.length === 0 && (
            <p style={{ fontSize: 13, color: 'var(--fg-muted)' }}>No matching playbooks found.</p>
          )}
          {relevantPlaybooks.map((pb) => (
            <div key={pb.id} style={{ marginTop: 8 }}>
              <Button
                size="sm"
                variant="primary"
                onClick={() => executePlaybookMutation.mutate(pb.id)}
                disabled={executePlaybookMutation.isPending}
              >
                {pb.name}
              </Button>
              {pb.description && (
                <span style={{ fontSize: 12, color: 'var(--fg-muted)', marginLeft: 8 }}>
                  {pb.description}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Summary */}
      <div className={styles.sectionHeader}>Summary</div>
      <p className={styles.panelDesc}>{safeText(selected.description)}</p>

      {/* Key Details */}
      <div className={styles.sectionHeader}>Key Details</div>
      <div className={styles.keyDetails}>
        {selected.actor && (
          <>
            <span className={styles.keyDetailsLabel}>Actor</span>
            <span className={styles.keyDetailsValue}>
              <Link to={`/actors/${encodeURIComponent(selected.actor)}`} className={styles.mention}>
                @{safeText(selected.actor)}
              </Link>
            </span>
          </>
        )}
        {safeText(
          selected.repo || selected.context_data?.repo || selected.context_data?.repository,
        ) && (
          <>
            <span className={styles.keyDetailsLabel}>Repository</span>
            <span className={styles.keyDetailsValue}>
              {safeText(
                selected.repo || selected.context_data?.repo || selected.context_data?.repository,
              )}
            </span>
          </>
        )}
        {safeText(
          selected.org || selected.context_data?.org || selected.context_data?.organization,
        ) && (
          <>
            <span className={styles.keyDetailsLabel}>Organization</span>
            <span className={styles.keyDetailsValue}>
              {safeText(
                selected.org || selected.context_data?.org || selected.context_data?.organization,
              )}
            </span>
          </>
        )}
        {safeText(selected.context_data?.action) && (
          <>
            <span className={styles.keyDetailsLabel}>Action</span>
            <span className={styles.keyDetailsValue}>{safeText(selected.context_data.action)}</span>
          </>
        )}
        {safeText(selected.context_data?.what_changed) && (
          <>
            <span className={styles.keyDetailsLabel}>What Changed</span>
            <span className={styles.keyDetailsValue}>
              {safeText(selected.context_data.what_changed)}
            </span>
          </>
        )}
        {selected.source_ip && (
          <>
            <span className={styles.keyDetailsLabel}>Source IP</span>
            <span className={styles.keyDetailsValue}>{safeText(selected.source_ip)}</span>
          </>
        )}
        {selected.triggered_at && (
          <>
            <span className={styles.keyDetailsLabel}>Triggered</span>
            <span className={styles.keyDetailsValue}>
              {formatRelativeShort(selected.triggered_at)}
            </span>
          </>
        )}
      </div>

      {/* Rule Info */}
      {selected.rule_id && (
        <>
          <div className={styles.sectionHeader}>Rule Info</div>
          <div className={styles.keyDetails}>
            <span className={styles.keyDetailsLabel}>Rule</span>
            <span className={styles.keyDetailsValue}>
              <Link to={`/rules?id=${selected.rule_id}`} className={styles.mention}>
                {safeText(selected.rule_name) || `Rule #${selected.rule_id}`}
              </Link>
            </span>
            {(selected.rule_category || safeText(selected.context_data?.category)) && (
              <>
                <span className={styles.keyDetailsLabel}>Category</span>
                <span className={styles.keyDetailsValue}>
                  <Label variant="muted">
                    {safeText(selected.rule_category || selected.context_data?.category)}
                  </Label>
                </span>
              </>
            )}
            <span className={styles.keyDetailsLabel}>Version</span>
            <span className={styles.keyDetailsValue}>v{selected.rule_version}</span>
            {selected.rule_description && (
              <>
                <span className={styles.keyDetailsLabel}>Description</span>
                <span className={styles.keyDetailsValue}>
                  {safeText(selected.rule_description)}
                </span>
              </>
            )}
          </div>
        </>
      )}

      {/* Detection Window */}
      {(selected.window_start || selected.window_end) && (
        <>
          <div className={styles.sectionHeader}>Detection Window</div>
          <div className={styles.keyDetails}>
            {selected.window_start && (
              <>
                <span className={styles.keyDetailsLabel}>Start</span>
                <span className={styles.keyDetailsValue}>
                  {formatCompact(selected.window_start)}
                </span>
              </>
            )}
            {selected.window_end && (
              <>
                <span className={styles.keyDetailsLabel}>End</span>
                <span className={styles.keyDetailsValue}>{formatCompact(selected.window_end)}</span>
              </>
            )}
          </div>
        </>
      )}

      {/* Assignment & Resolution */}
      <div className={styles.sectionHeader}>Assignment</div>
      <div className={styles.keyDetails}>
        <span className={styles.keyDetailsLabel}>Assigned To</span>
        <span className={styles.keyDetailsValue}>
          {selected.assigned_to ? (
            <Link
              to={`/actors/${encodeURIComponent(selected.assigned_to)}`}
              className={styles.mention}
            >
              @{safeText(selected.assigned_to)}
            </Link>
          ) : (
            <span className={styles.evidenceMuted}>Unassigned</span>
          )}
        </span>
        {selected.resolved_at && (
          <>
            <span className={styles.keyDetailsLabel}>Resolved At</span>
            <span className={styles.keyDetailsValue}>{formatCompact(selected.resolved_at)}</span>
          </>
        )}
        {selected.resolution_note && (
          <>
            <span className={styles.keyDetailsLabel}>Resolution</span>
            <span className={styles.keyDetailsValue}>{safeText(selected.resolution_note)}</span>
          </>
        )}
        {selected.chain_id && (
          <>
            <span className={styles.keyDetailsLabel}>Correlated Chain</span>
            <span className={styles.keyDetailsValue}>
              <Link to={`/threats?tab=chains&id=${selected.chain_id}`} className={styles.mention}>
                {selected.chain_id.slice(0, 8)}…
              </Link>
            </span>
          </>
        )}
      </div>

      {/* Linked Tickets */}
      {selected.tickets.length > 0 && (
        <>
          <div className={styles.sectionHeader}>Linked Tickets</div>
          <div className={styles.ticketList}>
            {selected.tickets.map((ticket) => (
              <a
                key={ticket.id}
                href={ticket.external_url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.ticketLink}
              >
                <span className={styles.ticketProvider}>{ticket.provider}</span>
                <span>{ticket.external_id}</span>
              </a>
            ))}
          </div>
        </>
      )}

      {/* Related Events */}
      {eventIds.length > 0 && (
        <>
          <div className={styles.sectionHeader}>Related Events</div>
          <div className={styles.relatedEventsSection}>
            {eventIds.length <= 5 ? (
              eventIds.map((eventId) => {
                const timelineEvent = timelineEvents.find((e) => e.id === eventId);
                return (
                  <Link key={eventId} to={`/events/${eventId}`} className={styles.relatedEventRow}>
                    <span className={styles.relatedEventId}>#{eventId}</span>
                    {timelineEvent && (
                      <>
                        <span className={styles.relatedEventAction}>{timelineEvent.action}</span>
                        {timelineEvent.actor && (
                          <span className={styles.relatedEventActor}>@{timelineEvent.actor}</span>
                        )}
                        <span className={styles.relatedEventTime}>
                          {formatRelativeShort(timelineEvent.created_at)}
                        </span>
                      </>
                    )}
                  </Link>
                );
              })
            ) : (
              <>
                {eventIds.slice(0, 3).map((eventId) => {
                  const timelineEvent = timelineEvents.find((e) => e.id === eventId);
                  return (
                    <Link
                      key={eventId}
                      to={`/events/${eventId}`}
                      className={styles.relatedEventRow}
                    >
                      <span className={styles.relatedEventId}>#{eventId}</span>
                      {timelineEvent && (
                        <>
                          <span className={styles.relatedEventAction}>{timelineEvent.action}</span>
                          {timelineEvent.actor && (
                            <span className={styles.relatedEventActor}>@{timelineEvent.actor}</span>
                          )}
                          <span className={styles.relatedEventTime}>
                            {formatRelativeShort(timelineEvent.created_at)}
                          </span>
                        </>
                      )}
                    </Link>
                  );
                })}
                <Link to={`/events?detection_id=${selected.id}`} className={styles.eventCountLink}>
                  View all {eventIds.length} events →
                </Link>
              </>
            )}
          </div>
        </>
      )}

      {/* Evidence */}
      {hasEntries(selected.context_data) && (
        <>
          <div className={styles.sectionHeader}>Evidence</div>
          <EvidenceDisplay data={selected.context_data} />
        </>
      )}

      {/* Investigation Timeline (inline, collapsible) */}
      <div className={styles.sectionHeader}>
        <button
          type="button"
          className={styles.expandToggle}
          onClick={() => setTimelineExpanded((v) => !v)}
          aria-expanded={timelineExpanded}
          aria-controls="timeline-section"
        >
          {timelineExpanded ? '▾' : '▸'} Investigation Timeline
        </button>
      </div>
      {timelineExpanded && (
        <div id="timeline-section" className={styles.timelineInline}>
          {timelineLoading && <Spinner />}
          {timelineError && (
            <ErrorBanner message="Failed to load timeline" onRetry={refetchTimeline} />
          )}
          {!timelineLoading && !timelineError && timelineEvents.length === 0 && (
            <p className={styles.evidenceMuted}>No timeline events yet.</p>
          )}
          {timelineEvents.map((event) => (
            <Link key={event.id} to={`/events/${event.id}`} className={styles.timelineEvent}>
              <div className={styles.timelineEventDot}>
                <SeverityDot severity="low" />
              </div>
              <div className={styles.timelineEventContent}>
                <div className={styles.timelineEventAction}>{event.action}</div>
                <div className={styles.timelineEventMeta}>
                  {event.actor && <span>@{event.actor}</span>}
                  {event.org && <span>· {event.org}</span>}
                  {event.repo && <span>· {event.repo}</span>}
                  {event.source_ip && <span>· {event.source_ip}</span>}
                </div>
                <div className={styles.timelineEventTime}>{formatCompact(event.created_at)}</div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Delete — subtle link at bottom */}
      <div className={styles.panelDeleteSection}>
        <button
          type="button"
          className={styles.deleteLink}
          onClick={() => {
            if (window.confirm('Delete this detection record? This action cannot be undone.')) {
              deleteMutation.mutate(selected.id);
            }
          }}
          disabled={deleteMutation.isPending}
        >
          {deleteMutation.isPending ? 'Deleting…' : 'Delete Detection'}
        </button>
      </div>
    </>
  );
}
