import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getHealthSettings, updateHealthSettings } from '../../api/healthSignals';
import styles from './HealthSettings.module.css';

/* ------------------------------------------------------------------ */
/*  Toggle component                                                    */
/* ------------------------------------------------------------------ */

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className={styles.toggle} role="switch" aria-checked={checked}>
      <div className={`${styles.toggleTrack} ${checked ? styles.toggleOn : ''}`}>
        <div className={styles.toggleThumb} />
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ display: 'none' }}
      />
    </label>
  );
}

/* ------------------------------------------------------------------ */
/*  Default values                                                      */
/* ------------------------------------------------------------------ */

interface HealthSettingsState {
  /* Repository Health Thresholds */
  staleRepoDays: number;
  stalePrDays: number;
  unreviewedDependabotDays: number;
  ciSkippedConsecutive: number;

  /* Access & Identity Thresholds */
  dormantMemberDays: number;
  patNoExpiryFlag: boolean;
  patStaleDays: number;
  outsideCollabFlag: boolean;

  /* License Health */
  licenseUtilizationPct: number;
  ghostMemberCost: number;

  /* Alerting Escalation (Future) */
  escalateCriticalDays: number;
  escalateStaleReposDays: number;
  escalateDormantDays: number;
  escalationDestination: string;
}

const DEFAULTS: HealthSettingsState = {
  staleRepoDays: 90,
  stalePrDays: 30,
  unreviewedDependabotDays: 60,
  ciSkippedConsecutive: 10,

  dormantMemberDays: 90,
  patNoExpiryFlag: true,
  patStaleDays: 90,
  outsideCollabFlag: true,

  licenseUtilizationPct: 80,
  ghostMemberCost: 19,

  escalateCriticalDays: 60,
  escalateStaleReposDays: 180,
  escalateDormantDays: 180,
  escalationDestination: 'Detection queue (internal)',
};

const ESCALATION_OPTIONS = [
  'Detection queue (internal)',
  'Slack — #security-alerts',
  'PagerDuty',
];

/* ------------------------------------------------------------------ */
/*  Page component                                                      */
/* ------------------------------------------------------------------ */

export function HealthSettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [toast, setToast] = useState<string | null>(null);

  const {
    data: savedSettings,
    isLoading: isLoadingSettings,
    isError: isLoadError,
    refetch,
  } = useQuery({
    queryKey: ['health-settings'],
    queryFn: getHealthSettings,
    staleTime: 60_000,
  });

  const [settings, setSettings] = useState<HealthSettingsState>({ ...DEFAULTS });
  const [hasHydrated, setHasHydrated] = useState(false);

  // Hydrate local state from server data once loaded
  if (savedSettings && !hasHydrated) {
    const merged = { ...DEFAULTS };
    for (const key of Object.keys(DEFAULTS) as (keyof HealthSettingsState)[]) {
      if (key in savedSettings) {
        (merged as Record<string, unknown>)[key] = savedSettings[key];
      }
    }
    setSettings(merged);
    setHasHydrated(true);
  }

  const saveMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => updateHealthSettings(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['health-settings'] });
      showToast('Settings saved successfully');
    },
    onError: () => {
      showToast('Failed to save settings');
    },
  });

  const update = useCallback(
    <K extends keyof HealthSettingsState>(key: K, value: HealthSettingsState[K]) => {
      setSettings((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  function showToast(message: string) {
    setToast(message);
    setTimeout(() => setToast(null), 3000);
  }

  function handleSave() {
    saveMutation.mutate(settings as unknown as Record<string, unknown>);
  }

  function handleReset() {
    setSettings({ ...DEFAULTS });
    showToast('Settings reset to defaults');
  }

  if (isLoadingSettings) {
    return (
      <div className={styles.page}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
          <Spinner size={28} />
        </div>
      </div>
    );
  }

  if (isLoadError) {
    return (
      <div className={styles.page}>
        <ErrorBanner message="Failed to load health settings" onRetry={() => void refetch()} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.headerRow}>
        <Button size="sm" onClick={() => navigate('/health')}>
          ← Back
        </Button>
        <h1 className={styles.pageTitle}>Health Settings</h1>
      </div>
      <p className={styles.pageSub}>
        Configure thresholds, escalation behavior, and data source options. Admin role required.
      </p>

      {/* ---- Repository Health Thresholds ---- */}
      <div className={styles.settingsGroup}>
        <div className={styles.settingsGroupTitle}>Repository Health Thresholds</div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Stale repo threshold</div>
            <div className={styles.settingsHint}>
              Repos with no push activity beyond this age are flagged stale
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.staleRepoDays}
              onChange={(e) => update('staleRepoDays', Number(e.target.value))}
              aria-label="Stale repo threshold in days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Stale PR threshold</div>
            <div className={styles.settingsHint}>
              Open PRs with no activity beyond this age are flagged
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.stalePrDays}
              onChange={(e) => update('stalePrDays', Number(e.target.value))}
              aria-label="Stale PR threshold in days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Unreviewed Dependabot alerts threshold</div>
            <div className={styles.settingsHint}>
              Alerts open beyond this age without dismissal/fix
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.unreviewedDependabotDays}
              onChange={(e) => update('unreviewedDependabotDays', Number(e.target.value))}
              aria-label="Unreviewed Dependabot alerts threshold in days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>CI skipped workflow signal</div>
            <div className={styles.settingsHint}>
              Flag workflows with this many consecutive skip/cancelled conclusions
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.ciSkippedConsecutive}
              onChange={(e) => update('ciSkippedConsecutive', Number(e.target.value))}
              aria-label="CI skipped workflow consecutive count"
            />
            <span className={styles.settingsUnit}>consecutive</span>
          </div>
        </div>
      </div>

      {/* ---- Access & Identity Thresholds ---- */}
      <div className={styles.settingsGroup}>
        <div className={styles.settingsGroupTitle}>Access &amp; Identity Thresholds</div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Dormant member threshold</div>
            <div className={styles.settingsHint}>
              Members with no audit activity beyond this age are flagged dormant
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.dormantMemberDays}
              onChange={(e) => update('dormantMemberDays', Number(e.target.value))}
              aria-label="Dormant member threshold in days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>PAT no-expiry flag</div>
            <div className={styles.settingsHint}>
              Flag personal access tokens created without an expiration date
            </div>
          </div>
          <div>
            <Toggle
              checked={settings.patNoExpiryFlag}
              onChange={(v) => update('patNoExpiryFlag', v)}
            />
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>PAT stale threshold</div>
            <div className={styles.settingsHint}>Flag PATs not used beyond this age</div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.patStaleDays}
              onChange={(e) => update('patStaleDays', Number(e.target.value))}
              aria-label="PAT stale threshold in days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Outside collaborator write/admin flag</div>
            <div className={styles.settingsHint}>
              Always flag outside collaborators with write or admin permission
            </div>
          </div>
          <div>
            <Toggle
              checked={settings.outsideCollabFlag}
              onChange={(v) => update('outsideCollabFlag', v)}
            />
          </div>
        </div>
      </div>

      {/* ---- License Health ---- */}
      <div className={styles.settingsGroup}>
        <div className={styles.settingsGroupTitle}>License Health</div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>License utilization warning threshold</div>
            <div className={styles.settingsHint}>
              Show warning when seat utilization exceeds this percentage
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              max={100}
              value={settings.licenseUtilizationPct}
              onChange={(e) => update('licenseUtilizationPct', Number(e.target.value))}
              aria-label="License utilization warning threshold percentage"
            />
            <span className={styles.settingsUnit}>%</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Ghost member cost attribution</div>
            <div className={styles.settingsHint}>
              Monthly cost per seat used to estimate recoverable spend from dormant members
            </div>
          </div>
          <div className={styles.settingsControl}>
            <span className={styles.settingsUnit}>$</span>
            <input
              className={styles.inputSm}
              type="number"
              min={0}
              value={settings.ghostMemberCost}
              onChange={(e) => update('ghostMemberCost', Number(e.target.value))}
              aria-label="Ghost member cost in dollars"
            />
          </div>
        </div>
      </div>

      {/* ---- Alerting Escalation (Future) ---- */}
      <div className={styles.settingsGroup}>
        <div className={styles.settingsGroupTitle}>Alerting Escalation (Future)</div>

        <div className={styles.infoBanner}>
          Health signals are <strong>informational only</strong> at this time. The settings below
          define when signals will be automatically escalated to the detection/alerting pipeline in a
          future release.
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Escalate critical signals after</div>
            <div className={styles.settingsHint}>
              Unactioned critical signals older than this are promoted to detections
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.escalateCriticalDays}
              onChange={(e) => update('escalateCriticalDays', Number(e.target.value))}
              aria-label="Escalate critical signals after days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Escalate stale repos after</div>
            <div className={styles.settingsHint}>
              Stale repos idle beyond this age escalate to a detection-grade alert
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.escalateStaleReposDays}
              onChange={(e) => update('escalateStaleReposDays', Number(e.target.value))}
              aria-label="Escalate stale repos after days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Escalate dormant members after</div>
            <div className={styles.settingsHint}>
              Dormant members still consuming licenses beyond this age escalate
            </div>
          </div>
          <div className={styles.settingsControl}>
            <input
              className={styles.inputSm}
              type="number"
              min={1}
              value={settings.escalateDormantDays}
              onChange={(e) => update('escalateDormantDays', Number(e.target.value))}
              aria-label="Escalate dormant members after days"
            />
            <span className={styles.settingsUnit}>days</span>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Escalation destination</div>
            <div className={styles.settingsHint}>
              Where promoted health signals are sent when threshold is exceeded
            </div>
          </div>
          <div>
            <select
              className={styles.selectSm}
              value={settings.escalationDestination}
              onChange={(e) => update('escalationDestination', e.target.value)}
              aria-label="Escalation destination"
            >
              {ESCALATION_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* ---- Baseline & Data Sources ---- */}
      <div className={styles.settingsGroup}>
        <div className={styles.settingsGroupTitle}>Baseline &amp; Data Sources</div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Last baseline import</div>
            <div className={styles.settingsHint}>
              Used to seed repo list, member list, secret scanning enrollment, and branch protection
              state
            </div>
          </div>
          <div className={styles.settingsControl}>
            <span className={styles.settingsUnit}>Mar 20, 2026</span>
            <Button size="sm" onClick={() => navigate('/integrations')}>
              → Integrations
            </Button>
          </div>
        </div>

        <div className={styles.settingsRow}>
          <div>
            <div className={styles.settingsLabel}>Ongoing signals from audit log</div>
            <div className={styles.settingsHint}>
              All event-derived signals update automatically as new audit events are ingested — no
              GitHub API polling required
            </div>
          </div>
          <Label variant="success">active</Label>
        </div>
      </div>

      {/* ---- Footer buttons ---- */}
      <div className={styles.footerActions}>
        <Button variant="primary" onClick={handleSave} disabled={saveMutation.isPending}>
          {saveMutation.isPending ? 'Saving…' : 'Save settings'}
        </Button>
        <Button onClick={handleReset}>Reset to defaults</Button>
      </div>

      {/* Toast notification */}
      {toast && (
        <div className={styles.toast} role="status" aria-live="polite">
          {toast}
        </div>
      )}
    </div>
  );
}
