import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDetectionTimeline } from '../../api/executive';
import type { TimelineEvent } from '../../api/executive';
import { getRawEvent } from '../../api/events';
import { Drawer } from '../../components/primitives/Drawer';
import { CodeBlock } from '../../components/primitives/CodeBlock';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { formatCompact } from '../../utils/dates';
import { GeoMap } from '../../components/charts/GeoMap';
import styles from './InvestigationTimeline.module.css';

type Severity = 'critical' | 'high' | 'medium' | 'low';

function isSeverity(v: string): v is Severity {
  return ['critical', 'high', 'medium', 'low'].includes(v);
}

/** Flatten a record into dot-notation key-value pairs for readable display. */
function flattenRecord(
  obj: Record<string, unknown>,
  prefix = '',
): Array<{ key: string; value: string }> {
  const rows: Array<{ key: string; value: string }> = [];
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (v === null || v === undefined) {
      rows.push({ key: fullKey, value: '—' });
    } else if (Array.isArray(v)) {
      rows.push({ key: fullKey, value: JSON.stringify(v) });
    } else if (typeof v === 'object') {
      rows.push(...flattenRecord(v as Record<string, unknown>, fullKey));
    } else {
      rows.push({ key: fullKey, value: String(v) });
    }
  }
  return rows;
}

function EventCard({ event, onClick }: { event: TimelineEvent; onClick: () => void }) {
  return (
    <div
      className={[styles.eventCard, event.is_sequence_step && styles.sequenceStep]
        .filter(Boolean)
        .join(' ')}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Event: ${event.action} at ${formatCompact(event.created_at)}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {event.is_sequence_step && (
        <div className={styles.stepBadge}>Step {(event.sequence_index ?? 0) + 1}</div>
      )}
      <div className={styles.eventTime}>{formatCompact(event.created_at)}</div>
      <div className={styles.eventAction}>{event.action}</div>
      <div className={styles.eventMeta}>
        {event.actor && (
          <a
            href={`/actors/${encodeURIComponent(event.actor)}`}
            className={styles.actorLink}
            onClick={(e) => e.stopPropagation()}
          >
            @{event.actor}
          </a>
        )}
        {event.repo && <span>· {event.repo}</span>}
      </div>
      {(event.geo_city || event.geo_country_code) && (
        <div className={styles.eventGeo}>
          📍 {[event.geo_city, event.geo_country_code].filter(Boolean).join(', ')}
          {event.source_ip && <> · {event.source_ip}</>}
        </div>
      )}
    </div>
  );
}

interface InvestigationTimelineProps {
  detectionId: number;
  onClose: () => void;
}

export function InvestigationTimeline({ detectionId, onClose }: InvestigationTimelineProps) {
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(null);
  const [showRawData, setShowRawData] = useState(false);

  const {
    data: timeline,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['detection-timeline', detectionId],
    queryFn: () => getDetectionTimeline(detectionId),
  });

  const { data: rawPayload, isLoading: rawLoading } = useQuery({
    queryKey: ['event-raw', selectedEvent?.id],
    queryFn: () => getRawEvent(selectedEvent!.id),
    enabled: selectedEvent !== null,
  });

  // Detect impossible-travel by checking for multiple distinct geo locations
  const geoPoints =
    timeline?.events
      .filter((e) => e.geo_latitude != null && e.geo_longitude != null)
      .map((e) => ({
        lat: e.geo_latitude!,
        lng: e.geo_longitude!,
        city: e.geo_city ?? '',
        country: e.geo_country_code ?? '',
      })) ?? [];

  const uniqueLocations = geoPoints.filter(
    (p, i, arr) => arr.findIndex((q) => q.lat === p.lat && q.lng === p.lng) === i,
  );
  const isImpossibleTravel =
    timeline?.detection_category === 'impossible_travel' && uniqueLocations.length >= 2;

  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.center}>
          <Spinner />
        </div>
      </div>
    );
  }

  if (isError || !timeline) {
    return (
      <div className={styles.page}>
        <ErrorBanner message="Failed to load timeline" onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>Investigation Timeline</div>
          <div className={styles.detectionTitle}>
            {isSeverity(timeline.detection_severity) && (
              <SeverityDot severity={timeline.detection_severity} />
            )}
            <span>{timeline.detection_title}</span>
            <Label
              variant={
                timeline.detection_severity === 'critical'
                  ? 'danger'
                  : timeline.detection_severity === 'high'
                    ? 'severe'
                    : 'attention'
              }
            >
              {timeline.detection_severity}
            </Label>
          </div>
        </div>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close timeline">
          ✕
        </button>
      </div>

      {isImpossibleTravel && (
        <div className={styles.mapContainer}>
          <GeoMap locations={uniqueLocations} />
        </div>
      )}

      <div className={styles.timeline}>
        {timeline.events.length === 0 && (
          <div className={styles.emptyState}>No events found for this detection</div>
        )}
        {timeline.events.map((event, idx) => (
          <div key={event.id} className={styles.timelineItem}>
            <div className={styles.timelineConnector}>
              <div
                className={[styles.timelineDot, event.is_sequence_step && styles.sequenceDot]
                  .filter(Boolean)
                  .join(' ')}
              />
              {idx < timeline.events.length - 1 && (
                <div
                  className={[
                    styles.timelineLine,
                    event.is_sequence_step &&
                      timeline.events[idx + 1]?.is_sequence_step &&
                      styles.sequenceLine,
                  ]
                    .filter(Boolean)
                    .join(' ')}
                />
              )}
            </div>
            <EventCard event={event} onClick={() => setSelectedEvent(event)} />
          </div>
        ))}
      </div>

      <Drawer
        open={selectedEvent !== null}
        onClose={() => setSelectedEvent(null)}
        title={selectedEvent?.action ?? 'Event Details'}
      >
        {selectedEvent && (
          <div className={styles.drawerContent}>
            <div className={styles.detailGrid}>
              <div className={styles.detailLabel}>Timestamp</div>
              <div>{formatCompact(selectedEvent.created_at)}</div>
              <div className={styles.detailLabel}>Action</div>
              <div>{selectedEvent.action}</div>
              <div className={styles.detailLabel}>Actor</div>
              <div>
                {selectedEvent.actor ? (
                  <a href={`/actors/${encodeURIComponent(selectedEvent.actor)}`}>
                    @{selectedEvent.actor}
                  </a>
                ) : (
                  '—'
                )}
              </div>
              <div className={styles.detailLabel}>Organization</div>
              <div>{selectedEvent.org ?? '—'}</div>
              <div className={styles.detailLabel}>Repository</div>
              <div>{selectedEvent.repo ?? '—'}</div>
              <div className={styles.detailLabel}>Source IP</div>
              <div>{selectedEvent.source_ip ?? '—'}</div>
              <div className={styles.detailLabel}>Location</div>
              <div>
                {[selectedEvent.geo_city, selectedEvent.geo_country_code]
                  .filter(Boolean)
                  .join(', ') || '—'}
              </div>
            </div>

            {Object.keys(selectedEvent.data).length > 0 && (
              <div className={styles.rawSection}>
                <div className={styles.dataHeader}>
                  <span className={styles.rawLabel}>Event Data</span>
                  <Button size="sm" variant="default" onClick={() => setShowRawData((v) => !v)}>
                    {showRawData ? 'Formatted' : 'Raw JSON'}
                  </Button>
                </div>
                {showRawData ? (
                  <CodeBlock>{JSON.stringify(selectedEvent.data, null, 2)}</CodeBlock>
                ) : (
                  <div className={styles.detailGrid}>
                    {flattenRecord(selectedEvent.data as Record<string, unknown>).map(
                      ({ key, value }) => (
                        <div key={key} className={styles.dataEntry}>
                          <div className={styles.detailLabel}>{key}</div>
                          <div>{value}</div>
                        </div>
                      ),
                    )}
                  </div>
                )}
              </div>
            )}

            {rawLoading && <Spinner />}
            {rawPayload && (
              <div className={styles.rawSection}>
                <div className={styles.rawLabel}>Raw Payload</div>
                <CodeBlock>{JSON.stringify(rawPayload, null, 2)}</CodeBlock>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
