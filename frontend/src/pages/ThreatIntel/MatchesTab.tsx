import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { listMatches } from '../../api/threatIntel';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { formatAbsolute } from '../../utils/dates';
import styles from './ThreatIntel.module.css';

const PAGE_SIZE = 50;

function severityClass(severity: string): string {
  if (severity === 'critical') return styles.severityCritical;
  if (severity === 'high') return styles.severityHigh;
  if (severity === 'medium') return styles.severityMedium;
  return styles.severityLow;
}

export function MatchesTab() {
  const [page, setPage] = useState(1);

  const {
    data: matchesData,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['threat-intel', 'matches', page],
    queryFn: () => listMatches({ page, page_size: PAGE_SIZE }),
  });

  const items = matchesData?.items ?? [];
  const total = matchesData?.total ?? 0;
  const total24h = matchesData?.total_24h ?? 0;
  const uniqueIndicators = matchesData?.unique_indicators ?? 0;
  const topFeed = matchesData?.top_feed ?? '—';

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner />
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner message="Failed to load matches" onRetry={refetch} />;
  }

  return (
    <div>
      <div className={styles.metricsRow}>
        <MetricCard value={String(total24h)} label="Matches (24h)" />
        <MetricCard value={String(uniqueIndicators)} label="Unique Indicators Matched" />
        <MetricCard value={topFeed} label="Top Matched Feed" />
      </div>

      {items.length === 0 ? (
        <div className={styles.emptyState}>
          No threat intelligence matches found. Matches appear when detections correlate with known
          threat indicators.
        </div>
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th scope="col">Detection</th>
                  <th scope="col">Matched Indicator</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Status</th>
                  <th scope="col">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {items.map((match) => (
                  <tr key={match.detection_id}>
                    <td>
                      <Link
                        to={`/threats/open?id=${match.detection_id}`}
                        className={styles.matchLink}
                      >
                        {match.title}
                      </Link>
                    </td>
                    <td>
                      {match.matched_indicator_value ? (
                        <>
                          <code>{match.matched_indicator_value}</code>
                          {match.matched_indicator_type && (
                            <span className={styles.typeBadge} style={{ marginLeft: 6 }}>
                              {match.matched_indicator_type}
                            </span>
                          )}
                        </>
                      ) : (
                        <span style={{ color: 'var(--fg-muted)' }}>—</span>
                      )}
                    </td>
                    <td>{match.actor ?? '—'}</td>
                    <td>
                      <span
                        className={[styles.statusBadge, severityClass(match.severity)].join(' ')}
                      >
                        {match.severity}
                      </span>
                    </td>
                    <td>{match.status}</td>
                    <td>{formatAbsolute(match.triggered_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            hasNext={page * PAGE_SIZE < total}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
