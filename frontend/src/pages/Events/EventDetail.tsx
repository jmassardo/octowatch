import { useState } from 'react';
import type { EventResponse } from '../../types/events';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { formatAbsolute } from '../../utils/dates';
import styles from './Events.module.css';

function actionVariant(action: string) {
  if (action.includes('destroy') || action.includes('delete') || action.includes('visibility'))
    return 'danger' as const;
  if (action.includes('access') || action.includes('rename')) return 'attention' as const;
  return 'muted' as const;
}

/**
 * Render a single value from the event `data` record in a human-friendly way.
 * Objects / arrays are serialised to compact JSON; primitives are converted to
 * strings. Null / undefined show an em-dash.
 */
function renderDataValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/**
 * Human-friendly detail view for a single audit-log event.
 *
 * Replaces the raw JSON `<pre>` block that was previously shown inside the
 * event detail modal.
 */
export function EventDetail({ event }: { event: EventResponse }) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className={styles.eventDetail}>
      <div className={styles.eventDetailGrid}>
        <div className={styles.eventDetailRow}>
          <span className={styles.eventDetailLabel}>Action</span>
          <Label variant={actionVariant(event.action)}>{event.action}</Label>
        </div>
        <div className={styles.eventDetailRow}>
          <span className={styles.eventDetailLabel}>Timestamp</span>
          <span>{formatAbsolute(event.created_at)}</span>
        </div>
        {event.actor && (
          <div className={styles.eventDetailRow}>
            <span className={styles.eventDetailLabel}>Actor</span>
            <span className={styles.mention}>@{event.actor}</span>
            {event.actor_is_bot && <Label variant="muted">bot</Label>}
          </div>
        )}
        {event.org && (
          <div className={styles.eventDetailRow}>
            <span className={styles.eventDetailLabel}>Organization</span>
            <span>{event.org}</span>
          </div>
        )}
        {event.repo && (
          <div className={styles.eventDetailRow}>
            <span className={styles.eventDetailLabel}>Repository</span>
            <span>{event.repo}</span>
          </div>
        )}
        {event.source_ip && (
          <div className={styles.eventDetailRow}>
            <span className={styles.eventDetailLabel}>Source IP</span>
            <code>{event.source_ip}</code>
            {event.geo_country_code && <span> · {event.geo_country_code}</span>}
            {event.geo_city && <span> · {event.geo_city}</span>}
          </div>
        )}
        {event.user_agent && (
          <div className={styles.eventDetailRow}>
            <span className={styles.eventDetailLabel}>User Agent</span>
            <span className={styles.eventDetailUa}>{event.user_agent}</span>
          </div>
        )}
        <div className={styles.eventDetailRow}>
          <span className={styles.eventDetailLabel}>Ingested</span>
          <span>{formatAbsolute(event.ingested_at)}</span>
        </div>
        <div className={styles.eventDetailRow}>
          <span className={styles.eventDetailLabel}>Source</span>
          <span>{event.ingestion_source}</span>
        </div>
      </div>

      {Object.keys(event.data).length > 0 && (
        <div className={styles.eventDetailSection}>
          <div className={styles.eventDetailSectionHeader}>
            <span>Additional Data</span>
            <Button size="sm" variant="default" onClick={() => setShowRaw((v) => !v)}>
              {showRaw ? 'Formatted' : 'Raw JSON'}
            </Button>
          </div>
          {showRaw ? (
            <pre className={styles.eventJson}>{JSON.stringify(event.data, null, 2)}</pre>
          ) : (
            <dl className={styles.eventDataList}>
              {Object.entries(event.data).map(([key, value]) => (
                <div key={key} className={styles.eventDataRow}>
                  <dt>{key}</dt>
                  <dd>{renderDataValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
