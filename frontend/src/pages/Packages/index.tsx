import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '../../components/common/PageHeader';
import { EmptyState } from '../../components/common/EmptyState';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import {
  getPackageSummary,
  getPackageAlerts,
  getPackageInventory,
  getStaleImages,
} from '../../api/packages';
import type {
  PackageSummary,
  PackageAlertList,
  PackageInventory,
  StaleImageList,
} from '../../api/packages';
import styles from './Packages.module.css';

type TabKey = 'overview' | 'inventory' | 'alerts' | 'container-health';

/* ── Severity badge ─────────────────────────────────────────────────────── */

function SeverityBadge({ severity }: { severity: string }) {
  const key = severity.toLowerCase();
  const cls =
    key === 'critical'
      ? styles.critical
      : key === 'high'
        ? styles.high
        : key === 'medium'
          ? styles.medium
          : key === 'low'
            ? styles.low
            : styles.none;
  return <span className={`${styles.badge} ${cls}`}>{severity}</span>;
}

/* ── Visibility badge ───────────────────────────────────────────────────── */

function VisibilityBadge({ visibility }: { visibility: string }) {
  const cls = visibility === 'public' ? styles.publicBadge : styles.privateBadge;
  return <span className={`${styles.badge} ${cls}`}>{visibility}</span>;
}

/* ── Overview tab ───────────────────────────────────────────────────────── */

function OverviewTab({
  summary,
  alerts,
}: {
  summary: PackageSummary | undefined;
  alerts: PackageAlertList | undefined;
}) {
  const recentAlerts = alerts?.alerts?.slice(0, 5) ?? [];

  return (
    <div>
      {/* By type breakdown */}
      {summary && Object.keys(summary.by_type).length > 0 && (
        <>
          <div className={styles.sectionTitle}>Packages by type</div>
          <div className={styles.metricGrid}>
            {Object.entries(summary.by_type).map(([type, count]) => (
              <MetricCard key={type} value={String(count)} label={type} />
            ))}
          </div>
        </>
      )}

      {/* Recent alerts */}
      <div className={styles.sectionTitle} style={{ marginTop: 24 }}>
        Recent alerts
      </div>
      {recentAlerts.length === 0 ? (
        <div className={styles.emptyState}>No package security alerts.</div>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Package</th>
                <th scope="col">Alert</th>
                <th scope="col">Severity</th>
                <th scope="col">Status</th>
                <th scope="col">Detected</th>
              </tr>
            </thead>
            <tbody>
              {recentAlerts.map((alert) => (
                <tr key={alert.id}>
                  <td>
                    {alert.package_org}/{alert.package_name}
                  </td>
                  <td>{alert.message}</td>
                  <td>
                    <SeverityBadge severity={alert.severity} />
                  </td>
                  <td>{alert.status}</td>
                  <td>{new Date(alert.detected_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Inventory tab ──────────────────────────────────────────────────────── */

function InventoryTab({ data }: { data: PackageInventory | undefined }) {
  const items = data?.items ?? [];

  if (items.length === 0) {
    return <div className={styles.emptyState}>No packages found.</div>;
  }

  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Org</th>
            <th scope="col">Type</th>
            <th scope="col">Visibility</th>
            <th scope="col">Versions</th>
            <th scope="col">Latest</th>
            <th scope="col">Last Published</th>
            <th scope="col">Flags</th>
          </tr>
        </thead>
        <tbody>
          {items.map((pkg) => (
            <tr key={pkg.id}>
              <td>
                <strong>{pkg.name}</strong>
                {pkg.repo && (
                  <div style={{ fontSize: 11, color: 'var(--fg-muted)' }}>{pkg.repo}</div>
                )}
              </td>
              <td>{pkg.org}</td>
              <td>{pkg.package_type}</td>
              <td>
                <VisibilityBadge visibility={pkg.visibility} />
              </td>
              <td>{pkg.versions_count}</td>
              <td>{pkg.latest_version ?? '—'}</td>
              <td>
                {pkg.last_published_at ? new Date(pkg.last_published_at).toLocaleDateString() : '—'}
              </td>
              <td>
                {pkg.is_stale && <span className={styles.warningIcon}>⏰</span>}
                {pkg.published_outside_actions && <span className={styles.warningIcon}>⚠️</span>}
                {pkg.published_by_external && <span className={styles.warningIcon}>🔓</span>}
                {!pkg.is_stale &&
                  !pkg.published_outside_actions &&
                  !pkg.published_by_external &&
                  '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Alerts tab ─────────────────────────────────────────────────────────── */

function AlertsTab({ data }: { data: PackageAlertList | undefined }) {
  const alerts = data?.alerts ?? [];

  if (alerts.length === 0) {
    return <div className={styles.emptyState}>No package security alerts.</div>;
  }

  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Package</th>
            <th scope="col">Type</th>
            <th scope="col">Severity</th>
            <th scope="col">Message</th>
            <th scope="col">Status</th>
            <th scope="col">Detected</th>
            <th scope="col">Resolved</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.id}>
              <td>
                {alert.package_org}/{alert.package_name}
              </td>
              <td>{alert.alert_type}</td>
              <td>
                <SeverityBadge severity={alert.severity} />
              </td>
              <td>{alert.message}</td>
              <td>{alert.status}</td>
              <td>{new Date(alert.detected_at).toLocaleString()}</td>
              <td>{alert.resolved_at ? new Date(alert.resolved_at).toLocaleString() : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Container Health tab ───────────────────────────────────────────────── */

function ContainerHealthTab({ data }: { data: StaleImageList | undefined }) {
  const images = data?.images ?? [];
  const threshold = data?.threshold_days ?? 90;

  return (
    <div>
      <div className={styles.sectionSub}>
        Container images not rebuilt in over {threshold} days.
      </div>
      {images.length === 0 ? (
        <div className={styles.emptyState}>All container images are up to date.</div>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Image</th>
                <th scope="col">Org</th>
                <th scope="col">Repo</th>
                <th scope="col">Last Rebuilt</th>
                <th scope="col">Days Since Rebuild</th>
                <th scope="col">Owner</th>
              </tr>
            </thead>
            <tbody>
              {images.map((img) => (
                <tr key={img.id}>
                  <td>
                    <strong>{img.name}</strong>
                  </td>
                  <td>{img.org}</td>
                  <td>{img.repo ?? '—'}</td>
                  <td>
                    {img.last_published_at
                      ? new Date(img.last_published_at).toLocaleDateString()
                      : 'Never'}
                  </td>
                  <td>
                    <span
                      style={{
                        color: img.days_since_rebuild > 180 ? 'var(--danger)' : 'var(--attention)',
                      }}
                    >
                      {img.days_since_rebuild} days
                    </span>
                  </td>
                  <td>{img.owner ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Main page ──────────────────────────────────────────────────────────── */

export function PackagesPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  const summaryQuery = useQuery({
    queryKey: ['packages', 'summary'],
    queryFn: getPackageSummary,
    staleTime: 60_000,
  });

  const alertsQuery = useQuery({
    queryKey: ['packages', 'alerts'],
    queryFn: () => getPackageAlerts({ status: 'open' }),
    staleTime: 60_000,
  });

  const inventoryQuery = useQuery({
    queryKey: ['packages', 'inventory'],
    queryFn: () => getPackageInventory(),
    staleTime: 60_000,
  });

  const staleQuery = useQuery({
    queryKey: ['packages', 'stale-images'],
    queryFn: () => getStaleImages(),
    staleTime: 60_000,
  });

  const isLoading =
    summaryQuery.isLoading ||
    alertsQuery.isLoading ||
    inventoryQuery.isLoading ||
    staleQuery.isLoading;
  const isError =
    summaryQuery.isError || alertsQuery.isError || inventoryQuery.isError || staleQuery.isError;

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    const retryAll = () => {
      void summaryQuery.refetch();
      void alertsQuery.refetch();
      void inventoryQuery.refetch();
      void staleQuery.refetch();
    };
    return <ErrorBanner message="Failed to load packages data" onRetry={retryAll} />;
  }

  const summary = summaryQuery.data;
  const hasData = summary != null && summary.total_packages > 0;

  return (
    <div className={styles.page}>
      <PageHeader
        title="Packages"
        description="Monitor package security posture, visibility, and container image health"
        showHelp
      />

      {/* ── Empty state when no packages synced ──────────────────────── */}
      {!hasData && (
        <EmptyState
          icon="📦"
          title="No packages synced yet"
          description="Package data will appear here once your GitHub organisations have been synced. Ensure at least one organisation with GitHub Packages is connected."
        />
      )}

      {/* ── Summary strip ────────────────────────────────────────────── */}
      {hasData && (
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(summary?.total_packages ?? 0)}
            label="Total Packages"
            helpText="Total number of packages across all monitored organisations."
          />
          <MetricCard
            value={String(summary?.public_packages ?? 0)}
            label="Public Packages"
            accent={summary != null && summary.public_packages > 0}
            helpText="Packages with public visibility — potential data exposure risk."
          />
          <MetricCard
            value={String(summary?.private_packages ?? 0)}
            label="Private Packages"
            helpText="Packages with private visibility."
          />
          <MetricCard
            value={String(summary?.stale_images ?? 0)}
            label="Stale Images"
            accent={summary != null && summary.stale_images > 0}
            helpText="Container images not rebuilt in over 90 days."
          />
          <MetricCard
            value={String(summary?.open_alerts ?? 0)}
            label="Open Alerts"
            accent={summary != null && summary.open_alerts > 0}
            helpText="Active security alerts requiring attention."
          />
        </div>
      )}

      {/* ── Tabs ─────────────────────────────────────────────────────── */}
      {hasData && (
        <div className={styles.tabs} role="tablist">
          {(
            [
              ['overview', 'Overview'],
              ['inventory', 'Inventory'],
              ['alerts', 'Alerts'],
              ['container-health', 'Container Health'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={activeTab === key}
              className={`${styles.tab} ${activeTab === key ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* ── Tab content ──────────────────────────────────────────────── */}
      {hasData && activeTab === 'overview' && (
        <OverviewTab summary={summary} alerts={alertsQuery.data} />
      )}
      {hasData && activeTab === 'inventory' && <InventoryTab data={inventoryQuery.data} />}
      {hasData && activeTab === 'alerts' && <AlertsTab data={alertsQuery.data} />}
      {hasData && activeTab === 'container-health' && <ContainerHealthTab data={staleQuery.data} />}
    </div>
  );
}
