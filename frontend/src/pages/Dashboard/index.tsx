import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { listDetections } from '../../api/detections';
import { listEvents } from '../../api/events';
import { getActionsVolumeReport } from '../../api/reports';
import {
  getDashboardConfig,
  updateDashboardConfig,
  getWidgetCatalog,
  type WidgetLayoutItem as ApiLayoutItem,
  type CatalogWidget,
} from '../../api/dashboardConfig';
import {
  getSystemHealth,
  getRepoHealth,
  getPatHealth,
  getUnifiedSecurity,
} from '../../api/healthSignals';
import { PageHeader } from '../../components/common/PageHeader';
import {
  OnboardingWizard,
  type OnboardingResult,
} from '../../components/GuidedTour/OnboardingWizard';
import { isOnboardingComplete } from '../../components/GuidedTour/onboardingStorage';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { WidgetGrid } from '../../components/widgets/WidgetGrid';
import { SecurityOverviewWidget } from '../../components/widgets/SecurityOverviewWidget';
import { WidgetCatalog } from '../../components/widgets/WidgetCatalog';
import { PersonaSelector } from '../../components/widgets/PersonaSelector';
import {
  createDashboardLayout,
  getWidgetDefinition,
  loadDashboardLayout,
  saveDashboardLayout,
  PERSONA_WIDGET_PRESETS,
} from '../../components/widgets/WidgetRegistry';
import type { DashboardPersona } from '../../components/widgets/WidgetRegistry';
import { StatPillConfigDrawer } from '../../components/widgets/StatPillConfig';
import {
  loadStatPillConfig,
  saveStatPillConfig,
} from '../../components/widgets/statPillConfigStorage';
import { useOrg } from '../../hooks/useOrg';
import type { ActionsVolumeBucket } from '../../types/reports';
import { formatRelative } from '../../utils/dates';
import styles from './Dashboard.module.css';

type DashboardView = 'widgets' | 'operations';
const VALID_VIEWS: DashboardView[] = ['widgets', 'operations'];

function ClickableValue({
  children,
  onClick,
  label,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
}) {
  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={label}
      className={styles.clickableValue}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
    >
      {children}
    </span>
  );
}

function StatPill({
  value,
  label,
  variant,
  onClick,
  helpText,
}: {
  value: string;
  label: string;
  variant?: 'danger' | 'success' | 'accent' | 'done';
  onClick?: () => void;
  helpText?: string;
}) {
  return (
    <div
      className={[styles.pill, variant && styles[variant], onClick && styles.pillClickable]
        .filter(Boolean)
        .join(' ')}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      aria-label={onClick ? `${value} ${label}` : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <span className={styles.pillVal}>{value}</span>&nbsp;{label}
      {helpText && (
        <span className={styles.helpIcon} title={helpText} aria-label={`Help: ${label}`}>
          ⓘ
        </span>
      )}
      {onClick && (
        <span className={styles.pillArrow} aria-hidden="true">
          →
        </span>
      )}
    </div>
  );
}

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

/** Convert persona preset widget IDs to API layout items with proper positioning. */
function presetToApiLayout(
  widgetIds: readonly string[],
  catalog: readonly CatalogWidget[],
): ApiLayoutItem[] {
  const catalogMap = new Map(catalog.map((w) => [w.id, w]));
  const items: ApiLayoutItem[] = [];
  let x = 0;
  let y = 0;
  let rowMaxH = 0;

  for (const id of widgetIds) {
    const cw = catalogMap.get(id);
    const w = cw?.default_w ?? 4;
    const h = cw?.default_h ?? 3;

    if (x + w > 12) {
      x = 0;
      y += rowMaxH;
      rowMaxH = 0;
    }

    items.push({ widget_id: id, x, y, w, h });
    x += w;
    rowMaxH = Math.max(rowMaxH, h);

    if (x >= 12) {
      x = 0;
      y += rowMaxH;
      rowMaxH = 0;
    }
  }

  return items;
}

export function DashboardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { selectedOrg, setSelectedOrg } = useOrg();
  const [searchParams, setSearchParams] = useSearchParams();
  const [widgetLayout, setWidgetLayout] = useState(() => loadDashboardLayout());
  const [showOnboarding, setShowOnboarding] = useState(() => !isOnboardingComplete());
  const [pillConfig, setPillConfig] = useState(() => loadStatPillConfig());
  const [pillConfigOpen, setPillConfigOpen] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [personaSelectorOpen, setPersonaSelectorOpen] = useState(false);

  // Fetch user's dashboard config from backend
  const configQuery = useQuery({
    queryKey: ['dashboard-config'],
    queryFn: getDashboardConfig,
    staleTime: 30_000,
  });

  // Fetch the widget catalog from backend
  const catalogQuery = useQuery({
    queryKey: ['dashboard-widgets'],
    queryFn: getWidgetCatalog,
    staleTime: 300_000,
  });

  const catalogWidgets = catalogQuery.data?.widgets ?? [];

  // Mutation to save layout to backend
  const saveMutation = useMutation({
    mutationFn: updateDashboardConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(['dashboard-config'], data);
    },
  });

  // Derive widget layout: prefer backend config, fallback to local storage
  const backendLayout = useMemo(() => {
    if (configQuery.data && configQuery.data.layout.length > 0) {
      return configQuery.data.layout.map((item) => ({
        id: item.widget_id,
        size: (getWidgetDefinition(item.widget_id)?.defaultSize ?? 'md') as 'sm' | 'md' | 'lg',
      }));
    }
    return null;
  }, [configQuery.data]);

  const effectiveWidgetLayout = backendLayout ?? widgetLayout;

  useEffect(() => {
    saveDashboardLayout(widgetLayout);
  }, [widgetLayout]);

  const rawView =
    searchParams.get('view') ?? (effectiveWidgetLayout.length > 0 ? 'widgets' : 'operations');
  const view: DashboardView = VALID_VIEWS.includes(rawView as DashboardView)
    ? (rawView as DashboardView)
    : effectiveWidgetLayout.length > 0
      ? 'widgets'
      : 'operations';

  function setView(nextView: DashboardView) {
    setSearchParams({ view: nextView }, { replace: true });
  }

  function handleOnboardingComplete(result: OnboardingResult) {
    const layout = createDashboardLayout(result.widgetIds);
    setWidgetLayout(layout);
    saveDashboardLayout(layout);
    setSelectedOrg(result.organizations.length === 1 ? (result.organizations[0] ?? '') : '');
    setShowOnboarding(false);
    setView('widgets');
  }

  // Active widget IDs for the catalog
  const activeWidgetIds = useMemo(
    () => new Set(effectiveWidgetLayout.map((item) => item.id)),
    [effectiveWidgetLayout],
  );

  // Add widget from catalog
  const handleAddWidget = useCallback(
    (widgetId: string) => {
      if (activeWidgetIds.has(widgetId)) return;
      const def = getWidgetDefinition(widgetId);
      const newLayout = [
        ...effectiveWidgetLayout,
        { id: widgetId, size: def?.defaultSize ?? 'md' },
      ];
      setWidgetLayout(newLayout);

      // Persist to backend
      const apiLayout: ApiLayoutItem[] = newLayout.map((item, idx) => {
        const cw = catalogWidgets.find((w) => w.id === item.id);
        return {
          widget_id: item.id,
          x: (idx * 4) % 12,
          y: Math.floor((idx * 4) / 12) * 3,
          w: cw?.default_w ?? 4,
          h: cw?.default_h ?? 3,
        };
      });
      saveMutation.mutate({ layout: apiLayout, persona: configQuery.data?.persona ?? '' });
    },
    [
      activeWidgetIds,
      effectiveWidgetLayout,
      catalogWidgets,
      saveMutation,
      configQuery.data?.persona,
    ],
  );

  // Remove widget from catalog
  const handleRemoveWidget = useCallback(
    (widgetId: string) => {
      const newLayout = effectiveWidgetLayout.filter((item) => item.id !== widgetId);
      setWidgetLayout(newLayout);

      // Persist to backend
      const apiLayout: ApiLayoutItem[] = newLayout.map((item, idx) => {
        const cw = catalogWidgets.find((w) => w.id === item.id);
        return {
          widget_id: item.id,
          x: (idx * 4) % 12,
          y: Math.floor((idx * 4) / 12) * 3,
          w: cw?.default_w ?? 4,
          h: cw?.default_h ?? 3,
        };
      });
      saveMutation.mutate({ layout: apiLayout, persona: configQuery.data?.persona ?? '' });
    },
    [effectiveWidgetLayout, catalogWidgets, saveMutation, configQuery.data?.persona],
  );

  // Persona selection handler
  const handlePersonaSelect = useCallback(
    (personaId: string) => {
      const presetIds = PERSONA_WIDGET_PRESETS[personaId as DashboardPersona];
      if (!presetIds) return;

      const layout = createDashboardLayout([...presetIds]);
      setWidgetLayout(layout);
      saveDashboardLayout(layout);

      // Persist to backend
      const apiLayout = presetToApiLayout(presetIds, catalogWidgets);
      saveMutation.mutate({ layout: apiLayout, persona: personaId });
      setPersonaSelectorOpen(false);
      setView('widgets');
    },
    [catalogWidgets, saveMutation, setView],
  );

  const orgLabel = !selectedOrg || selectedOrg === 'all' ? 'All organizations' : selectedOrg;
  const orgParam = selectedOrg && selectedOrg !== 'all' ? selectedOrg : undefined;

  const { data: detections } = useQuery({
    queryKey: ['detections', 'open', selectedOrg],
    queryFn: () => listDetections({ status: 'open', org: orgParam, page_size: 100 }),
    staleTime: 5 * 60 * 1000,
  });

  const { data: events } = useQuery({
    queryKey: ['events', 'recent', selectedOrg],
    queryFn: () => listEvents({ page_size: 10, sort: 'created_at_desc', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  const { data: calendarEvents } = useQuery({
    queryKey: ['events', 'calendar', selectedOrg],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  const { data: actionsReport } = useQuery({
    queryKey: ['reports', 'actions-volume-dashboard', selectedOrg],
    queryFn: () => getActionsVolumeReport({ window_days: 7, granularity: 'daily', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  const { data: repoHealth } = useQuery({
    queryKey: ['health-signals', 'repo-health-ops'],
    queryFn: () => getRepoHealth(),
    staleTime: 5 * 60 * 1000,
  });

  const { data: patHealth } = useQuery({
    queryKey: ['health-signals', 'pat-health-ops'],
    queryFn: () => getPatHealth(),
    staleTime: 5 * 60 * 1000,
  });

  const { data: systemHealth } = useQuery({
    queryKey: ['health-signals', 'system-dashboard'],
    queryFn: getSystemHealth,
    staleTime: 5 * 60 * 1000,
  });

  const { data: unifiedSecurity } = useQuery({
    queryKey: ['health-signals', 'unified-security-dashboard'],
    queryFn: getUnifiedSecurity,
    staleTime: 5 * 60 * 1000,
  });

  const actionsBuckets = (actionsReport?.data ?? []) as unknown as ActionsVolumeBucket[];
  const totalWorkflowRuns = actionsBuckets.reduce(
    (sum, bucket) => sum + (bucket.workflow_runs_total ?? 0),
    0,
  );
  const succeededWorkflowRuns = actionsBuckets.reduce(
    (sum, bucket) => sum + (bucket.workflow_runs_succeeded ?? 0),
    0,
  );
  const failedWorkflowRuns = actionsBuckets.reduce(
    (sum, bucket) => sum + (bucket.workflow_runs_failed ?? 0),
    0,
  );
  const workflowSuccessRate =
    totalWorkflowRuns > 0 ? ((succeededWorkflowRuns / totalWorkflowRuns) * 100).toFixed(1) : null;

  const openThreats = detections?.total ?? 0;
  const eventCountLabel = formatCount(events?.total ?? 0);
  const uniqueActors = new Set(
    (calendarEvents?.items ?? []).map((event) => event.actor).filter(Boolean),
  ).size;

  return (
    <div className={styles.page}>
      <PageHeader
        title={`Dashboard · ${orgLabel}`}
        description={
          systemHealth?.last_event_at
            ? `Last synced: ${formatRelative(systemHealth.last_event_at)}`
            : 'Activity across your organizations'
        }
        showHelp
      />

      <div className={styles.viewToggle}>
        <button
          className={[styles.viewBtn, view === 'widgets' && styles.viewActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setView('widgets')}
        >
          My Dashboard
        </button>
        <button
          className={[styles.viewBtn, view === 'operations' && styles.viewActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setView('operations')}
        >
          Operations
        </button>
        <div className={styles.viewToggleSpacer} />
        {view === 'widgets' && (
          <div className={styles.customizeActions}>
            <Button type="button" size="sm" variant="default" onClick={() => setCatalogOpen(true)}>
              Add widgets
            </Button>
            <Button
              type="button"
              size="sm"
              variant="default"
              onClick={() => setPersonaSelectorOpen(true)}
            >
              Change layout
            </Button>
            {saveMutation.isPending && <span className={styles.savingIndicator}>Saving…</span>}
          </div>
        )}
      </div>

      {view === 'widgets' ? (
        <div className={styles.widgetSection}>
          {effectiveWidgetLayout.length === 0 ? (
            <div className={styles.widgetEmptyState}>
              <svg
                width="48"
                height="48"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"
                />
              </svg>
              <h3>Build your custom dashboard</h3>
              <p>Choose a persona for a recommended layout, or add widgets manually.</p>
              <div className={styles.widgetEmptyActions}>
                <button
                  className={styles.widgetAddBtn}
                  onClick={() => setPersonaSelectorOpen(true)}
                >
                  Choose a persona
                </button>
                <button
                  className={styles.widgetAddBtn}
                  onClick={() => {
                    const defaultLayout = createDashboardLayout([
                      'security-overview',
                      'detection-summary',
                      'posture-gauge',
                      'event-volume',
                    ]);
                    setWidgetLayout(defaultLayout);
                  }}
                >
                  Add starter widgets
                </button>
              </div>
            </div>
          ) : (
            <WidgetGrid layout={effectiveWidgetLayout} onChange={setWidgetLayout} />
          )}
        </div>
      ) : (
        <>
          {systemHealth != null && (
            <div
              className={[styles.systemHealthBar, systemHealth.gap_detected && styles.healthWarning]
                .filter(Boolean)
                .join(' ')}
            >
              <span
                className={[
                  styles.systemHealthDot,
                  systemHealth.gap_detected ? styles.warn : styles.ok,
                ].join(' ')}
              />
              {systemHealth.gap_detected ? (
                <span>
                  Ingestion gap detected
                  {systemHealth.gap_duration_minutes != null && (
                    <> — {systemHealth.gap_duration_minutes}m of missing data</>
                  )}
                </span>
              ) : (
                <span>
                  System healthy
                  {systemHealth.last_event_at && (
                    <> · Last event: {formatRelative(systemHealth.last_event_at)}</>
                  )}
                </span>
              )}
            </div>
          )}

          <div className={styles.pillsHeader}>
            <div className={styles.pills}>
              <StatPill
                value={eventCountLabel || '—'}
                label="total events"
                helpText="Total audit log events stored across all orgs. Source: events table."
                onClick={() => navigate('/events')}
              />
              <StatPill
                value={workflowSuccessRate != null ? `${workflowSuccessRate}%` : '—'}
                label="pipeline success"
                helpText="7-day Actions workflow success rate. Calculated from workflow_run.completed events."
                variant={
                  workflowSuccessRate != null && parseFloat(workflowSuccessRate) >= 90
                    ? 'success'
                    : undefined
                }
                onClick={() => navigate('/velocity')}
              />
              <StatPill
                value={String(uniqueActors || '—')}
                label="active devs"
                variant="done"
                helpText="Unique human actors (non-bot) seen in audit log events over the last 30 days."
                onClick={() => navigate('/devactivity')}
              />
              <StatPill
                value={String(repoHealth?.stale.length ?? '—')}
                label="stale repos"
                helpText="Repositories with no activity in the last 90 days."
                onClick={() => navigate('/health')}
              />
              <StatPill
                value={String(patHealth?.summary.stale_90d_count ?? '—')}
                label="stale PATs"
                helpText="Personal access tokens with no use in the last 90 days."
                onClick={() => navigate('/health/access')}
              />
              <StatPill
                value={String(patHealth?.summary.no_expiry_count ?? '—')}
                label="PATs no expiry"
                variant={(patHealth?.summary.no_expiry_count ?? 0) > 0 ? 'danger' : undefined}
                helpText="Personal access tokens with no expiration date set."
                onClick={() => navigate('/health/access')}
              />
              <StatPill
                value={String(unifiedSecurity?.secret_scanning.open ?? '—')}
                label="secret alerts"
                variant={(unifiedSecurity?.secret_scanning.open ?? 0) > 0 ? 'danger' : undefined}
                helpText="Open GitHub secret scanning alerts across all organizations (GHAS)."
                onClick={() => navigate('/advanced-security/secrets')}
              />
              <StatPill
                value={String(unifiedSecurity?.code_scanning.open ?? '—')}
                label="code alerts"
                helpText="Open GitHub code scanning (CodeQL) alerts across all organizations (GHAS)."
                onClick={() => navigate('/advanced-security/code')}
              />
              <StatPill
                value={String(unifiedSecurity?.dependabot.open ?? '—')}
                label="dependabot"
                helpText="Open Dependabot vulnerability alerts across all organizations (GHAS)."
                onClick={() => navigate('/advanced-security/dependabot')}
              />
            </div>
            <button
              className={styles.pillsCustomize}
              onClick={() => setPillConfigOpen(true)}
              aria-label="Customize metrics"
              title="Customize metrics"
            >
              <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                <path d="M8 0a8.2 8.2 0 01.701.031C11.444.199 13.5 1.5 14.5 3.5c.5 1 .75 2.5.5 4-.25 1-.75 2-1.5 3-.5.5-1 1-1.5 1.5l-.5.5V14a1 1 0 01-1 1H5.5a1 1 0 01-1-1v-1.5l-.5-.5c-.5-.5-1-1-1.5-1.5-.75-1-1.25-2-1.5-3-.25-1.5 0-3 .5-4C2.5 1.5 4.556.199 7.299.031A8.2 8.2 0 018 0zM5 5.5a1 1 0 10-2 0 1 1 0 002 0zm4-1a1 1 0 110 2 1 1 0 010-2zM7.5 9.5a1 1 0 10-2 0 1 1 0 002 0z" />
              </svg>
            </button>
          </div>

          <StatPillConfigDrawer
            open={pillConfigOpen}
            onClose={() => setPillConfigOpen(false)}
            config={pillConfig}
            onSave={(cfg) => {
              setPillConfig(cfg);
              saveStatPillConfig(cfg);
              setPillConfigOpen(false);
            }}
          />

          {systemHealth != null && systemHealth.gap_detected && (
            <div className={styles.ingestionBanner}>
              <span className={styles.ingestionIcon}>⚠</span>
              <span>
                Data ingestion gap detected
                {systemHealth.gap_duration_minutes != null && (
                  <> — {systemHealth.gap_duration_minutes} minutes of missing data</>
                )}
                . Some health signals may be incomplete.
              </span>
            </div>
          )}

          <div className={styles.grid}>
            <div className={styles.flex1}>
              <SecurityOverviewWidget detections={detections?.items ?? []} />
            </div>

            <div className={styles.sidebar}>
              <Card>
                <CardHeader>Platform alerts</CardHeader>
                <div className={styles.alerts}>
                  <div className={styles.alertRow}>
                    <span
                      className={styles.alertIcon}
                      style={{ color: failedWorkflowRuns > 0 ? 'var(--danger)' : 'var(--success)' }}
                    >
                      {failedWorkflowRuns > 0 ? '⚠' : '✓'}
                    </span>
                    <div>
                      Workflow runs:{' '}
                      <ClickableValue
                        onClick={() => navigate('/velocity')}
                        label={`${succeededWorkflowRuns} succeeded — view velocity`}
                      >
                        <strong>{succeededWorkflowRuns} succeeded</strong>
                      </ClickableValue>
                      ,{' '}
                      <ClickableValue
                        onClick={() => navigate('/velocity')}
                        label={`${failedWorkflowRuns} failed — view velocity`}
                      >
                        <strong>{failedWorkflowRuns} failed</strong>
                      </ClickableValue>
                      {totalWorkflowRuns > 0 ? ` (${workflowSuccessRate}% success)` : ''}
                    </div>
                  </div>
                  <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                    <span className={styles.alertIcon} style={{ color: 'var(--attention)' }}>
                      ⚡
                    </span>
                    <div>
                      Events volume:{' '}
                      <ClickableValue
                        onClick={() => navigate('/events')}
                        label={`${formatCount(calendarEvents?.total ?? 0)} events — view all events`}
                      >
                        <strong>{formatCount(calendarEvents?.total ?? 0)} events</strong>
                      </ClickableValue>{' '}
                      tracked
                    </div>
                  </div>
                  <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                    <span
                      className={styles.alertIcon}
                      style={{ color: openThreats > 0 ? 'var(--attention)' : 'var(--success)' }}
                    >
                      {openThreats > 0 ? '⚠' : '✓'}
                    </span>
                    <div>
                      Active detections:{' '}
                      <ClickableValue
                        onClick={() => navigate('/threats')}
                        label={`${openThreats} investigating — view threats`}
                      >
                        <strong>{openThreats} investigating</strong>
                      </ClickableValue>
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </>
      )}

      <OnboardingWizard
        open={showOnboarding}
        onClose={() => setShowOnboarding(false)}
        onComplete={handleOnboardingComplete}
      />

      <WidgetCatalog
        open={catalogOpen}
        onClose={() => setCatalogOpen(false)}
        widgets={catalogWidgets}
        activeWidgetIds={activeWidgetIds}
        onAdd={handleAddWidget}
        onRemove={handleRemoveWidget}
      />

      <PersonaSelector
        open={personaSelectorOpen}
        onSelect={handlePersonaSelect}
        onSkip={() => setPersonaSelectorOpen(false)}
      />
    </div>
  );
}
