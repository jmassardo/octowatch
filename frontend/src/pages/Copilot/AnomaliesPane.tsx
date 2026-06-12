import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '../../components/primitives/Button';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Label } from '../../components/primitives/Label';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getCopilotAnomalies } from '../../api/copilotMetrics';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

const SEVERITY_VARIANT = {
  high: 'danger',
  medium: 'attention',
  low: 'muted',
} as const;

type SeverityFilter = 'high' | 'medium' | 'low' | null;

interface DetectionRule {
  id: string;
  name: string;
  description: string;
  thresholds: string;
  enabled: boolean;
}

const DETECTION_RULES: DetectionRule[] = [
  {
    id: 'acceptance-rate-drop',
    name: 'Acceptance Rate Drop',
    description: 'Fires when the 3-day acceptance rate drops significantly from baseline',
    thresholds: 'High: >15% drop, Medium: >10%, Low: >5%',
    enabled: true,
  },
  {
    id: 'active-user-change',
    name: 'Active User Count Change',
    description: 'Fires when active user count changes >20% from baseline',
    thresholds: 'High: >20% change',
    enabled: true,
  },
  {
    id: 'feature-usage-spike',
    name: 'Feature Usage Spike',
    description: "Fires when a feature's engaged users spike >200% from baseline",
    thresholds: 'Medium: >200% increase',
    enabled: true,
  },
  {
    id: 'sudden-user-drop',
    name: 'Sudden Active User Drop',
    description: 'Fires when daily active users drop >30% from 7-day average',
    thresholds: 'High: >30% drop',
    enabled: true,
  },
  {
    id: 'model-switching',
    name: 'Model Switching Detection',
    description: "Fires when a model's usage share changes >20% in one day",
    thresholds: 'Medium: >20% share change',
    enabled: true,
  },
  {
    id: 'bulk-policy-changes',
    name: 'Bulk Policy Changes',
    description: 'Fires when >5 Copilot policy audit events occur in 24 hours',
    thresholds: 'High: >5 events in 24h',
    enabled: true,
  },
];

const METRIC_OPTIONS = [
  'Acceptance rate',
  'Active users',
  'Feature usage',
  'Model distribution',
  'Custom',
] as const;

const CONDITION_OPTIONS = ['drops below', 'rises above', 'changes by'] as const;

const SEVERITY_OPTIONS = ['high', 'medium', 'low'] as const;

const detectionRuleColumns: ColumnDef<DetectionRule>[] = [
  {
    key: 'name',
    header: 'Name',
    sortable: true,
    render: (row) => <strong>{row.name}</strong>,
    sortValue: (row) => row.name,
    width: '180px',
  },
  {
    key: 'description',
    header: 'Description',
    render: (row) => row.description,
    width: '300px',
  },
  {
    key: 'thresholds',
    header: 'Thresholds',
    render: (row) => <code style={{ fontSize: 12 }}>{row.thresholds}</code>,
    width: '220px',
  },
  {
    key: 'status',
    header: 'Status',
    render: (row) => (
      <span title="Custom rules coming soon">
        <Label variant={row.enabled ? 'success' : 'muted'}>
          {row.enabled ? 'Enabled' : 'Disabled'}
        </Label>
      </span>
    ),
    width: '100px',
  },
];

export function AnomaliesPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const {
    data: anomalyData,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['copilot', 'anomalies', orgParam],
    queryFn: () => getCopilotAnomalies(orgParam),
    staleTime: 30 * 60 * 1000,
  });
  const anomalies = anomalyData?.anomalies ?? [];

  const anomalyListRef = useRef<HTMLDivElement>(null);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>(null);
  const [teamModal, setTeamModal] = useState<string | null>(null);
  const [rulesExpanded, setRulesExpanded] = useState(false);
  const [customRuleModalOpen, setCustomRuleModalOpen] = useState(false);
  const [customRuleForm, setCustomRuleForm] = useState({
    name: '',
    metric: METRIC_OPTIONS[0] as string,
    condition: CONDITION_OPTIONS[0] as string,
    threshold: '',
    severity: 'medium' as (typeof SEVERITY_OPTIONS)[number],
  });
  const [customRuleSaved, setCustomRuleSaved] = useState(false);

  function handleCountClick() {
    if (anomalyListRef.current) {
      anomalyListRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }

  function handleSeverityClick(severity: 'high' | 'medium' | 'low') {
    setSeverityFilter((prev) => (prev === severity ? null : severity));
  }

  function handleCustomRuleSave() {
    setCustomRuleSaved(true);
    setTimeout(() => {
      setCustomRuleSaved(false);
      setCustomRuleModalOpen(false);
      setCustomRuleForm({
        name: '',
        metric: METRIC_OPTIONS[0],
        condition: CONDITION_OPTIONS[0],
        threshold: '',
        severity: 'medium',
      });
    }, 2500);
  }

  const filteredAnomalies = severityFilter
    ? anomalies.filter((a) => a.severity === severityFilter)
    : anomalies;

  const selectedAnomaly = teamModal ? anomalies.find((a) => a.team === teamModal) : null;

  const detectionRulesSection = (
    <div style={{ marginTop: 24 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <button
          type="button"
          onClick={() => setRulesExpanded((prev) => !prev)}
          aria-expanded={rulesExpanded}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 14,
            fontWeight: 600,
            color: 'var(--fg-default)',
            padding: 0,
          }}
        >
          <span
            style={{
              display: 'inline-block',
              transform: rulesExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 0.15s ease',
            }}
          >
            ▶
          </span>
          Detection Rules ({DETECTION_RULES.length} active)
        </button>
        {rulesExpanded && (
          <Button variant="primary" size="sm" onClick={() => setCustomRuleModalOpen(true)}>
            ➕ Create Custom Rule
          </Button>
        )}
      </div>
      {rulesExpanded && (
        <DataTable<DetectionRule>
          columns={detectionRuleColumns}
          data={DETECTION_RULES}
          rowKey={(row) => row.id}
          emptyMessage="No detection rules configured"
        />
      )}
    </div>
  );

  return (
    <>
      {anomalyData?.error && (
        <SampleDataBanner message={anomalyData.message ?? 'Anomaly data is unavailable.'} />
      )}

      {isError && (
        <ErrorBanner message="Failed to load anomaly data" onRetry={() => void refetch()} />
      )}
      {isLoading && <Spinner />}

      {!isLoading && !isError && anomalies.length === 0 && !anomalyData?.error && (
        <>
          <div className={styles.insightNote} style={{ textAlign: 'center', padding: '32px 0' }}>
            ✅ No anomalies detected. This is a good sign!
          </div>
          {detectionRulesSection}
        </>
      )}

      {!isLoading && !isError && anomalies.length > 0 && (
        <>
          <div className={styles.insightNote}>
            <span
              className={styles.anomalyCountClickable}
              role="button"
              tabIndex={0}
              onClick={handleCountClick}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleCountClick();
                }
              }}
            >
              {anomalies.length} anomalies
            </span>{' '}
            detected in the last 7 days based on usage pattern analysis
            {severityFilter && (
              <span style={{ marginLeft: 8, fontSize: 11 }}>
                (filtered: {severityFilter}){' '}
                <span
                  className={styles.clickableStat}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSeverityFilter(null)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSeverityFilter(null);
                    }
                  }}
                  style={{ fontSize: 11 }}
                >
                  clear
                </span>
              </span>
            )}
          </div>

          <div className={styles.anomalyList} ref={anomalyListRef}>
            {filteredAnomalies.map((anomaly) => (
              <div key={anomaly.id} className={styles.anomalyCard}>
                <div className={styles.anomalyHeader}>
                  <span
                    className={styles.severityBadgeClickable}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSeverityClick(anomaly.severity)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleSeverityClick(anomaly.severity);
                      }
                    }}
                  >
                    <Label variant={SEVERITY_VARIANT[anomaly.severity]}>
                      {anomaly.severity.toUpperCase()}
                    </Label>
                  </span>
                  <span className={styles.anomalyTime}>{anomaly.timestamp}</span>
                </div>
                <div className={styles.anomalyTitle}>{anomaly.title}</div>
                <div className={styles.anomalyDesc}>{anomaly.description}</div>
                <div className={styles.anomalyMeta}>
                  {anomaly.affected_count !== undefined && anomaly.affected_count > 0 && (
                    <span style={{ marginRight: 12 }}>
                      Affected: <strong>{anomaly.affected_count}</strong>
                    </span>
                  )}
                  Team:{' '}
                  <span
                    className={styles.anomalyTeamClickable}
                    role="button"
                    tabIndex={0}
                    onClick={() => setTeamModal(anomaly.team)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setTeamModal(anomaly.team);
                      }
                    }}
                  >
                    {anomaly.team}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {detectionRulesSection}

          {/* Team anomaly context modal */}
          <Modal
            open={teamModal !== null}
            onClose={() => setTeamModal(null)}
            title={teamModal ? `${teamModal} team — anomaly context` : 'Team context'}
            width={520}
          >
            {selectedAnomaly && (
              <div>
                <table className={styles.modalTable}>
                  <thead>
                    <tr>
                      <th scope="col">Detail</th>
                      <th scope="col">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Team</td>
                      <td style={{ fontWeight: 500 }}>{selectedAnomaly.team}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Anomaly</td>
                      <td>{selectedAnomaly.title}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Severity</td>
                      <td>{selectedAnomaly.severity.toUpperCase()}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Detected</td>
                      <td>{selectedAnomaly.timestamp}</td>
                    </tr>
                  </tbody>
                </table>
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--fg-muted)',
                    lineHeight: 1.6,
                    margin: '12px 0 0',
                  }}
                >
                  {selectedAnomaly.description}
                </p>
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--fg-muted)',
                    lineHeight: 1.6,
                    margin: '12px 0 0',
                  }}
                >
                  Team-level Copilot usage trends, member-specific breakdowns, and historical
                  anomaly patterns require the Copilot Metrics API integration.
                </p>
              </div>
            )}
          </Modal>
        </>
      )}

      {/* Custom Rule Modal */}
      <Modal
        open={customRuleModalOpen}
        onClose={() => {
          setCustomRuleModalOpen(false);
          setCustomRuleSaved(false);
        }}
        title="Create Custom Detection Rule"
        width={520}
      >
        {customRuleSaved ? (
          <div style={{ textAlign: 'center', padding: '24px 0' }} role="alert" aria-live="polite">
            <p style={{ fontSize: 16, fontWeight: 600 }}>
              🚧 Custom detection rules will be available in a future release.
            </p>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', marginTop: 8 }}>
              Your rule configuration has been noted. Stay tuned!
            </p>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleCustomRuleSave();
            }}
            style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
          >
            <div>
              <label
                htmlFor="custom-rule-name"
                style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}
              >
                Rule name
              </label>
              <input
                id="custom-rule-name"
                type="text"
                value={customRuleForm.name}
                onChange={(e) => setCustomRuleForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Low acceptance rate alert"
                required
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid var(--border-default)',
                  fontSize: 14,
                  background: 'var(--canvas-subtle)',
                  color: 'var(--fg-default)',
                }}
              />
            </div>

            <div>
              <label
                htmlFor="custom-rule-metric"
                style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}
              >
                Metric to monitor
              </label>
              <select
                id="custom-rule-metric"
                value={customRuleForm.metric}
                onChange={(e) => setCustomRuleForm((f) => ({ ...f, metric: e.target.value }))}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid var(--border-default)',
                  fontSize: 14,
                  background: 'var(--canvas-subtle)',
                  color: 'var(--fg-default)',
                }}
              >
                {METRIC_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="custom-rule-condition"
                style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}
              >
                Condition
              </label>
              <select
                id="custom-rule-condition"
                value={customRuleForm.condition}
                onChange={(e) => setCustomRuleForm((f) => ({ ...f, condition: e.target.value }))}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid var(--border-default)',
                  fontSize: 14,
                  background: 'var(--canvas-subtle)',
                  color: 'var(--fg-default)',
                }}
              >
                {CONDITION_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="custom-rule-threshold"
                style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}
              >
                Threshold value
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <input
                  id="custom-rule-threshold"
                  type="number"
                  min={0}
                  max={100}
                  value={customRuleForm.threshold}
                  onChange={(e) => setCustomRuleForm((f) => ({ ...f, threshold: e.target.value }))}
                  placeholder="e.g. 15"
                  required
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: '1px solid var(--border-default)',
                    fontSize: 14,
                    background: 'var(--canvas-subtle)',
                    color: 'var(--fg-default)',
                  }}
                />
                <span style={{ fontSize: 14, fontWeight: 500 }}>%</span>
              </div>
            </div>

            <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
              <legend style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>Severity</legend>
              <div style={{ display: 'flex', gap: 16 }}>
                {SEVERITY_OPTIONS.map((sev) => (
                  <label key={sev} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <input
                      type="radio"
                      name="custom-rule-severity"
                      value={sev}
                      checked={customRuleForm.severity === sev}
                      onChange={() => setCustomRuleForm((f) => ({ ...f, severity: sev }))}
                    />
                    <span style={{ fontSize: 13, textTransform: 'capitalize' }}>{sev}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
              <Button type="submit" variant="primary">
                Save Rule
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
