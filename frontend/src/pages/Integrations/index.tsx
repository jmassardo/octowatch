import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  listTicketingConfigs,
  listNotificationConfigs,
} from '../../api/integrations';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { SyncPanel } from './SyncPanel';
import { SyncRunHistory } from './SyncRunHistory';
import { ManualIngestPanel } from './ManualIngestPanel';
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
  status: string;
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

function MktCard({ integration, onConfigure, onInstall }: { integration: MarketplaceIntegration; onConfigure?: () => void; onInstall?: () => void }) {
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
        <span
          className={`${styles.statusLabel} ${className} ${styles.clickableStatus}`}
          tabIndex={0}
          aria-label={`${integration.name} status: ${label}`}
          onClick={isInstalled ? onConfigure : onInstall}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              (isInstalled ? onConfigure : onInstall)?.();
            }
          }}
        >
          <span className={styles.statusDot} />
          {label}
        </span>
        {isInstalled ? (
          <Button size="sm" onClick={onConfigure}>Configure</Button>
        ) : (
          <Button variant="primary" size="sm" onClick={onInstall}>Install</Button>
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
  onFileSelect,
}: {
  title: string;
  icon: React.ReactNode;
  accept: string;
  formatHint: string;
  helperText: React.ReactNode;
  onFileSelect?: (file: File) => void;
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
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file && onFileSelect) onFileSelect(file);
            e.target.value = '';
          }}
        />
      </div>
      <p className={styles.importHelp}>{helperText}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function IntegrationsPage() {
  const [statusOverrides, setStatusOverrides] = useState<Record<string, IntegrationStatus>>({});
  const [configTarget, setConfigTarget] = useState<MarketplaceIntegration | null>(null);
  const [importedFiles, setImportedFiles] = useState<RecentImport[]>([]);
  const [importDetail, setImportDetail] = useState<RecentImport | null>(null);

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

  function handleFileImport(file: File, type: string) {
    const entry: RecentImport = {
      file: file.name,
      type,
      size: formatFileSize(file.size),
      importedAt: new Date().toISOString().replace('T', ' ').slice(0, 16),
      records: 0,
      status: 'Processing',
    };
    setImportedFiles((prev) => [entry, ...prev]);
    setTimeout(() => {
      setImportedFiles((prev) =>
        prev.map((f) =>
          f.file === file.name && f.status === 'Processing'
            ? { ...f, status: 'Completed', records: Math.floor(Math.random() * 50000) + 1000 }
            : f,
        ),
      );
    }, 2000);
  }

  const allImports = [...importedFiles, ...RECENT_IMPORTS];

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
          {integrations.map((integration) => {
            const effective = { ...integration, status: statusOverrides[integration.name] ?? integration.status };
            return (
              <MktCard
                key={integration.name}
                integration={effective}
                onConfigure={() => setConfigTarget(effective)}
                onInstall={() => setStatusOverrides((prev) => ({ ...prev, [integration.name]: 'configured' }))}
              />
            );
          })}
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
            onFileSelect={(file) => handleFileImport(file, 'Audit Log')}
          />
          <ImportCard
            title="Copilot Metrics Import"
            icon={<MetricsFileIcon />}
            accept=".json"
            formatHint="Accepts .json · GitHub Copilot Metrics API format"
            helperText={
              <>Fetch via: <code>GET /orgs/&#123;org&#125;/copilot/metrics</code></>
            }
            onFileSelect={(file) => handleFileImport(file, 'Copilot Metrics')}
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
            {allImports.map((row) => (
              <tr key={`${row.file}-${row.importedAt}`}>
                <td>{row.file}</td>
                <td>{row.type}</td>
                <td>{row.size}</td>
                <td>{row.importedAt}</td>
                <td>
                  {row.records > 0 ? (
                    <span
                      className={styles.clickableRecord}
                      role="button"
                      tabIndex={0}
                      onClick={() => setImportDetail(row)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setImportDetail(row);
                        }
                      }}
                    >
                      {row.records.toLocaleString()}
                    </span>
                  ) : '—'}
                </td>
                <td>
                  <span className={`${styles.statusBadge} ${row.status === 'Completed' ? styles.badgeSuccess : ''}`}>
                    {row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Enterprise Sync */}
      <section>
        <h2 className={styles.sectionTitle}>Enterprise Sync</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <SyncPanel />
          <SyncRunHistory />
        </div>
      </section>

      {/* Import Data */}
      <section>
        <h2 className={styles.sectionTitle}>Import Data</h2>
        <ManualIngestPanel />
      </section>

      <Modal open={!!configTarget} onClose={() => setConfigTarget(null)} title={configTarget ? `Configure ${configTarget.name}` : ''}>
        {configTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <p style={{ margin: 0 }}><strong>Status:</strong> {statusMeta(configTarget.status).label}</p>
            <p style={{ margin: 0 }}><strong>Description:</strong> {configTarget.description}</p>
            <p style={{ margin: 0, color: 'var(--fg-muted)', fontSize: 13 }}>
              Configuration settings for {configTarget.name} integration. Connect via API key or OAuth flow.
            </p>
          </div>
        )}
      </Modal>

      <Modal open={!!importDetail} onClose={() => setImportDetail(null)} title="Import details" width={420}>
        {importDetail && (
          <dl className={styles.importDetail}>
            <div><dt>File</dt><dd>{importDetail.file}</dd></div>
            <div><dt>Type</dt><dd>{importDetail.type}</dd></div>
            <div><dt>Size</dt><dd>{importDetail.size}</dd></div>
            <div><dt>Records imported</dt><dd>{importDetail.records.toLocaleString()}</dd></div>
            <div><dt>Imported at</dt><dd>{importDetail.importedAt}</dd></div>
            <div><dt>Status</dt><dd>{importDetail.status}</dd></div>
            <p className={styles.importNote}>
              If any rows were skipped or had errors, details are available in the processing log.
            </p>
          </dl>
        )}
      </Modal>
    </div>
  );
}
