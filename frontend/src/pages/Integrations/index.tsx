import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  listTicketingConfigs,
  listNotificationConfigs,
} from '../../api/integrations';
import { Button } from '../../components/primitives/Button';
import styles from './Integrations.module.css';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type IntegrationStatus = 'connected' | 'configured' | 'not_installed';

interface MarketplaceIntegration {
  name: string;
  description: string;
  icon: React.ReactNode;
  status: IntegrationStatus;
  iconBg: string;
}

interface RecentImport {
  file: string;
  type: string;
  size: string;
  importedAt: string;
  records: number;
  status: 'Completed';
}

/* ------------------------------------------------------------------ */
/*  Static data                                                        */
/* ------------------------------------------------------------------ */

const RECENT_IMPORTS: RecentImport[] = [
  { file: 'audit-log-2025-06-01.csv', type: 'Audit Log', size: '14.2 MB', importedAt: '2025-06-01 09:32', records: 48_210, status: 'Completed' },
  { file: 'copilot-metrics-may.json', type: 'Copilot Metrics', size: '2.1 MB', importedAt: '2025-05-28 14:15', records: 1_340, status: 'Completed' },
  { file: 'audit-log-2025-05-15.json', type: 'Audit Log', size: '38.7 MB', importedAt: '2025-05-15 11:04', records: 125_800, status: 'Completed' },
];

/* ------------------------------------------------------------------ */
/*  Icons                                                              */
/* ------------------------------------------------------------------ */

function GitHubEnterpriseIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2a10 10 0 00-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.56 9.56 0 0112 6.84c.85 0 1.71.12 2.51.34 1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0012 2z" fill="white" />
    </svg>
  );
}

function SlackIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="8" cy="12" r="2" fill="#E01E5A" />
      <circle cx="12" cy="8" r="2" fill="#36C5F0" />
      <circle cx="16" cy="12" r="2" fill="#2EB67D" />
      <circle cx="12" cy="16" r="2" fill="#ECB22E" />
    </svg>
  );
}

function SentinelIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M13 3l7 14H6L13 3z" fill="white" fillOpacity="0.9" />
      <path d="M13 9v4M13 15h.01" stroke="#0078d4" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function SplunkIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 18L12 4l7 14H5z" fill="white" fillOpacity="0.85" />
      <path d="M12 10v4" stroke="#1a1a1a" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function PagerDutyIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="white" strokeWidth="2" fill="none" />
      <circle cx="12" cy="12" r="3" fill="white" />
    </svg>
  );
}

function JiraIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 13l4-4 2 2 6-6" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 5h6v6" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 16V4m0 0l-4 4m4-4l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function LogFileIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="2" width="16" height="20" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 7h8M8 11h8M8 15h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function MetricsFileIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M7 17V13M12 17V9M17 17V7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Marketplace card component                                         */
/* ------------------------------------------------------------------ */

function statusMeta(status: IntegrationStatus): { label: string; className: string } {
  switch (status) {
    case 'connected':
      return { label: 'Connected', className: styles.statusConnected };
    case 'configured':
      return { label: 'Configured', className: styles.statusConfigured };
    case 'not_installed':
      return { label: 'Not installed', className: styles.statusNotInstalled };
  }
}

function MktCard({ integration }: { integration: MarketplaceIntegration }) {
  const { label, className } = statusMeta(integration.status);
  const isInstalled = integration.status !== 'not_installed';

  return (
    <div className={styles.mktCard} data-testid={`mkt-card-${integration.name.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className={styles.mktCardHeader}>
        <div className={styles.mktCardIcon} style={{ backgroundColor: integration.iconBg }}>
          {integration.icon}
        </div>
        <div className={styles.mktCardInfo}>
          <p className={styles.mktCardName}>{integration.name}</p>
          <p className={styles.mktCardDesc}>{integration.description}</p>
        </div>
      </div>
      <div className={styles.mktCardFooter}>
        <span className={`${styles.statusLabel} ${className}`}>
          <span className={styles.statusDot} />
          {label}
        </span>
        {isInstalled ? (
          <Button size="sm">Configure</Button>
        ) : (
          <Button variant="primary" size="sm">Install</Button>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Import drop zone component                                         */
/* ------------------------------------------------------------------ */

function ImportCard({
  title,
  icon,
  accept,
  formatHint,
  helperText,
}: {
  title: string;
  icon: React.ReactNode;
  accept: string;
  formatHint: string;
  helperText: React.ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleClick() {
    inputRef.current?.click();
  }

  return (
    <div className={styles.importCard}>
      <div className={styles.importCardHeader}>
        <span className={styles.importCardHeaderIcon}>{icon}</span>
        {title}
      </div>
      <div
        className={styles.importDrop}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        aria-label={`Upload ${title}`}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleClick();
          }
        }}
      >
        <div className={styles.importDropIcon}>
          <UploadIcon />
        </div>
        <p className={styles.importDropText}>Drop file here or browse</p>
        <p className={styles.importDropHint}>{formatHint}</p>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className={styles.hiddenInput}
          aria-hidden="true"
          tabIndex={-1}
        />
      </div>
      <p className={styles.importHelp}>{helperText}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

export function IntegrationsPage() {
  /* Keep API hooks alive so integration data is cached for future use */
  useQuery({ queryKey: ['ticketing-configs'], queryFn: listTicketingConfigs });
  useQuery({ queryKey: ['notification-configs'], queryFn: listNotificationConfigs });

  const integrations: MarketplaceIntegration[] = [
    {
      name: 'GitHub Enterprise',
      description: 'Connect your GitHub Enterprise instance for audit log streaming and Copilot metrics.',
      icon: <GitHubEnterpriseIcon />,
      status: 'connected',
      iconBg: '#24292f',
    },
    {
      name: 'Slack',
      description: 'Send real-time alerts and weekly digest reports to Slack channels.',
      icon: <SlackIcon />,
      status: 'connected',
      iconBg: '#4a154b',
    },
    {
      name: 'Microsoft Sentinel',
      description: 'Forward normalized security events to Microsoft Sentinel for SIEM correlation.',
      icon: <SentinelIcon />,
      status: 'not_installed',
      iconBg: '#0078d4',
    },
    {
      name: 'Splunk',
      description: 'Stream audit events and Copilot metrics to Splunk via HEC.',
      icon: <SplunkIcon />,
      status: 'not_installed',
      iconBg: '#1a1a1a',
    },
    {
      name: 'PagerDuty',
      description: 'Trigger PagerDuty incidents for critical security detections.',
      icon: <PagerDutyIcon />,
      status: 'configured',
      iconBg: '#06ac38',
    },
    {
      name: 'Jira',
      description: 'Automatically create Jira issues for security findings and track remediation.',
      icon: <JiraIcon />,
      status: 'not_installed',
      iconBg: '#0052CC',
    },
  ];

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div>
        <h1 className={styles.pageTitle}>Integrations</h1>
        <p className={styles.pageSub}>
          Connect external services, import data, and extend OctoWatch capabilities
        </p>
      </div>

      {/* Marketplace grid */}
      <section>
        <h2 className={styles.sectionTitle}>Marketplace</h2>
        <div className={styles.mktGrid}>
          {integrations.map((integration) => (
            <MktCard key={integration.name} integration={integration} />
          ))}
        </div>
      </section>

      {/* Data Import */}
      <section>
        <h2 className={styles.sectionTitle}>Data Import</h2>
        <p className={styles.sectionDesc}>
          Import exported data files to analyze without live API access — great for
          evaluating OctoWatch before full deployment or filling historical gaps.
        </p>
        <div className={styles.importGrid}>
          <ImportCard
            title="Audit Log Import"
            icon={<LogFileIcon />}
            accept=".csv,.json"
            formatHint="Accepts .csv or .json · max 500 MB"
            helperText={
              <>Export from GitHub Enterprise: <code>Settings → Audit log → Export CSV</code></>
            }
          />
          <ImportCard
            title="Copilot Metrics Import"
            icon={<MetricsFileIcon />}
            accept=".json"
            formatHint="Accepts .json · GitHub Copilot Metrics API format"
            helperText={
              <>Fetch via: <code>GET /orgs/&#123;org&#125;/copilot/metrics</code></>
            }
          />
        </div>
      </section>

      {/* Recent imports table */}
      <section>
        <h2 className={styles.sectionTitle}>Recent imports</h2>
        <table className={styles.recentTable}>
          <thead>
            <tr>
              <th>File</th>
              <th>Type</th>
              <th>Size</th>
              <th>Imported at</th>
              <th>Records</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {RECENT_IMPORTS.map((row) => (
              <tr key={row.file}>
                <td>{row.file}</td>
                <td>{row.type}</td>
                <td>{row.size}</td>
                <td>{row.importedAt}</td>
                <td>{row.records.toLocaleString()}</td>
                <td>
                  <span className={`${styles.statusBadge} ${styles.badgeSuccess}`}>
                    {row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
