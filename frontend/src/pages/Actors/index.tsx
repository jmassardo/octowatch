import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  getActorProfile,
  getActorEvents,
  getActorDetections,
  getActorLocations,
} from '../../api/actors';
import type { ActorProfile, ActorEvent, ActorDetection } from '../../api/actors';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { GeoMap } from '../../components/charts/GeoMap';
import { formatCompact } from '../../utils/dates';
import styles from './Actors.module.css';

type TabKey = 'activity' | 'detections' | 'geo';
type Severity = 'critical' | 'high' | 'medium' | 'low';

function isSeverity(v: string): v is Severity {
  return ['critical', 'high', 'medium', 'low'].includes(v);
}

function RiskMeter({ score }: { score: number }) {
  const level =
    score >= 75 ? 'critical' : score >= 50 ? 'high' : score >= 25 ? 'medium' : 'low';
  const color =
    level === 'critical'
      ? 'var(--danger)'
      : level === 'high'
        ? 'var(--severe)'
        : level === 'medium'
          ? 'var(--attention)'
          : 'var(--success)';

  return (
    <div className={styles.riskMeter}>
      <div className={styles.riskBar}>
        <div
          className={styles.riskFill}
          style={{ width: `${Math.min(score, 100)}%`, background: color }}
        />
      </div>
      <span className={styles.riskScore} style={{ color }}>
        {score}
      </span>
      <Label
        variant={
          level === 'critical'
            ? 'danger'
            : level === 'high'
              ? 'severe'
              : level === 'medium'
                ? 'attention'
                : 'done'
        }
      >
        {level}
      </Label>
    </div>
  );
}

function ActivityTab({ login }: { login: string }) {
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['actor-events', login, page],
    queryFn: () => getActorEvents(login, { page, page_size: pageSize }),
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load events" onRetry={refetch} />;
  if (!data || data.items.length === 0) {
    return <div className={styles.emptyTab}>No activity found</div>;
  }

  return (
    <div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Time</th>
            <th>Action</th>
            <th>Repository</th>
            <th>Source IP</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((evt: ActorEvent) => (
            <tr key={evt.id}>
              <td className={styles.mono}>{formatCompact(evt.created_at)}</td>
              <td>{evt.action}</td>
              <td>{evt.repo ?? '—'}</td>
              <td className={styles.mono}>{evt.source_ip ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination
        page={page}
        pageSize={pageSize}
        total={data.total}
        hasNext={data.has_next}
        onPageChange={setPage}
      />
    </div>
  );
}

function DetectionsTab({ login }: { login: string }) {
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['actor-detections', login, page],
    queryFn: () => getActorDetections(login, { page, page_size: pageSize }),
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load detections" onRetry={refetch} />;
  if (!data || data.items.length === 0) {
    return <div className={styles.emptyTab}>No detections found</div>;
  }

  return (
    <div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Triggered</th>
            <th>Title</th>
            <th>Severity</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((d: ActorDetection) => (
            <tr key={d.id}>
              <td className={styles.mono}>{formatCompact(d.triggered_at)}</td>
              <td>
                <Link to="/threats" className={styles.link}>
                  {d.title}
                </Link>
              </td>
              <td>
                {isSeverity(d.severity) && <SeverityDot severity={d.severity} />}
                {' '}{d.severity}
              </td>
              <td>
                <Label variant={d.status === 'open' ? 'danger' : 'muted'}>
                  {d.status}
                </Label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination
        page={page}
        pageSize={pageSize}
        total={data.total}
        hasNext={data.has_next}
        onPageChange={setPage}
      />
    </div>
  );
}

function GeoTab({ login }: { login: string }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['actor-locations', login],
    queryFn: () => getActorLocations(login),
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load locations" onRetry={refetch} />;
  if (!data || data.locations.length === 0) {
    return <div className={styles.emptyTab}>No location data available</div>;
  }

  const geoPoints = data.locations
    .filter((loc) => loc.latitude != null && loc.longitude != null)
    .map((loc) => ({
      lat: loc.latitude!,
      lng: loc.longitude!,
      city: loc.city ?? '',
      country: loc.country_code ?? '',
    }));

  return (
    <div>
      {geoPoints.length > 0 && <GeoMap locations={geoPoints} height={350} />}
      <table className={styles.table}>
        <thead>
          <tr>
            <th>City</th>
            <th>Country</th>
            <th>Events</th>
            <th>Last Seen</th>
          </tr>
        </thead>
        <tbody>
          {data.locations.map((loc, idx) => (
            <tr key={idx}>
              <td>{loc.city ?? '—'}</td>
              <td>{loc.country_code ?? '—'}</td>
              <td>{loc.event_count}</td>
              <td className={styles.mono}>{loc.last_seen ? formatCompact(loc.last_seen) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProfileHeader({ profile }: { profile: ActorProfile }) {
  return (
    <div className={styles.profileHeader}>
      <img
        src={`https://github.com/${profile.login}.png?size=80`}
        alt={profile.login}
        className={styles.avatar}
        width={64}
        height={64}
      />
      <div className={styles.profileInfo}>
        <h1 className={styles.profileName}>@{profile.login}</h1>
        <div className={styles.profileMeta}>
          <span>{profile.event_count} events</span>
          <span>{profile.detection_count} detections</span>
          {profile.first_seen && (
            <span>Active since {formatCompact(profile.first_seen)}</span>
          )}
        </div>
        <RiskMeter score={profile.risk_score} />
      </div>
    </div>
  );
}

export function ActorsPage() {
  const { login } = useParams<{ login: string }>();
  const [tab, setTab] = useState<TabKey>('activity');

  const {
    data: profile,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['actor-profile', login],
    queryFn: () => getActorProfile(login!),
    enabled: !!login,
  });

  if (!login) {
    return (
      <div className={styles.page}>
        <ErrorBanner message="No actor login specified" />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.center}><Spinner /></div>
      </div>
    );
  }

  if (isError || !profile) {
    return (
      <div className={styles.page}>
        <ErrorBanner message={`Failed to load profile for @${login}`} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <ProfileHeader profile={profile} />

      <div className={styles.tabBar}>
        {(['activity', 'detections', 'geo'] as const).map((t) => (
          <button
            key={t}
            className={[styles.tabBtn, tab === t && styles.tabActive]
              .filter(Boolean)
              .join(' ')}
            onClick={() => setTab(t)}
          >
            {t === 'activity' ? '📋 Activity' : t === 'detections' ? '🛡️ Detections' : '🌍 Locations'}
          </button>
        ))}
      </div>

      <div className={styles.tabContent}>
        {tab === 'activity' && <ActivityTab login={login} />}
        {tab === 'detections' && <DetectionsTab login={login} />}
        {tab === 'geo' && <GeoTab login={login} />}
      </div>
    </div>
  );
}
