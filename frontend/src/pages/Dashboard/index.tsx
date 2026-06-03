import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getDashboardConfig,
  updateDashboardConfig,
  getWidgetCatalog,
  type WidgetLayoutItem as ApiLayoutItem,
  type CatalogWidget,
} from '../../api/dashboardConfig';
import { getSystemHealth } from '../../api/healthSignals';
import { PageHeader } from '../../components/common/PageHeader';
import {
  OnboardingWizard,
  type OnboardingResult,
} from '../../components/GuidedTour/OnboardingWizard';
import { isOnboardingComplete } from '../../components/GuidedTour/onboardingStorage';
import { Button } from '../../components/primitives/Button';
import { CreateCustomWidgetDialog } from '../../components/widgets/CreateCustomWidgetDialog';
import { WidgetGrid } from '../../components/widgets/WidgetGrid';
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
import { useOrg } from '../../hooks/useOrg';
import { formatRelative } from '../../utils/dates';
import styles from './Dashboard.module.css';

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
  const queryClient = useQueryClient();
  const { selectedOrg, setSelectedOrg } = useOrg();
  const [widgetLayout, setWidgetLayout] = useState(() => loadDashboardLayout());
  const [showOnboarding, setShowOnboarding] = useState(() => !isOnboardingComplete());
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [personaSelectorOpen, setPersonaSelectorOpen] = useState(false);
  const [customWidgetDialogOpen, setCustomWidgetDialogOpen] = useState(false);

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
      // Sync persisted layout back to local state
      if (data.layout.length > 0) {
        setWidgetLayout(
          data.layout.map((item) => ({
            id: item.widget_id,
            size: (getWidgetDefinition(item.widget_id)?.defaultSize ?? 'md') as 'sm' | 'md' | 'lg',
          })),
        );
      }
    },
  });

  // Seed widget layout from backend config on initial load
  const backendSeeded = useRef(false);
  useEffect(() => {
    if (!backendSeeded.current && configQuery.data && configQuery.data.layout.length > 0) {
      backendSeeded.current = true;
      const seeded = configQuery.data.layout.map((item) => ({
        id: item.widget_id,
        size: (getWidgetDefinition(item.widget_id)?.defaultSize ?? 'md') as 'sm' | 'md' | 'lg',
      }));
      setWidgetLayout(seeded);
    }
  }, [configQuery.data]);

  // After mutation success, sync backend response back into local state
  // (keeps local state authoritative while staying in sync with persisted data)
  const effectiveWidgetLayout = widgetLayout;

  useEffect(() => {
    saveDashboardLayout(widgetLayout);
  }, [widgetLayout]);

  // Listen for the custom widget creation event dispatched by CustomQueryWidget
  useEffect(() => {
    function handleOpenDialog() {
      setCustomWidgetDialogOpen(true);
    }
    window.addEventListener('octowatch:open-custom-widget-dialog', handleOpenDialog);
    return () => {
      window.removeEventListener('octowatch:open-custom-widget-dialog', handleOpenDialog);
    };
  }, []);

  // Handler: add newly created custom widget to the dashboard
  const handleCustomWidgetCreated = useCallback(
    (widgetId: string) => {
      const def = getWidgetDefinition(widgetId);
      const newLayout = [
        ...effectiveWidgetLayout,
        { id: widgetId, size: def?.defaultSize ?? ('md' as const) },
      ];
      setWidgetLayout(newLayout);

      const apiLayout: ApiLayoutItem[] = newLayout.map((item, idx) => {
        const cw = catalogWidgets.find((w) => w.id === item.id);
        return {
          widget_id: item.id,
          x: (idx * 4) % 12,
          y: Math.floor((idx * 4) / 12) * 3,
          w: cw?.default_w ?? 6,
          h: cw?.default_h ?? 3,
        };
      });
      saveMutation.mutate({ layout: apiLayout, persona: configQuery.data?.persona ?? '' });
    },
    [effectiveWidgetLayout, catalogWidgets, saveMutation, configQuery.data?.persona],
  );

  function handleOnboardingComplete(result: OnboardingResult) {
    const layout = createDashboardLayout(result.widgetIds);
    setWidgetLayout(layout);
    saveDashboardLayout(layout);
    setSelectedOrg(result.organizations.length === 1 ? (result.organizations[0] ?? '') : '');
    setShowOnboarding(false);
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
    },
    [catalogWidgets, saveMutation],
  );

  const orgLabel = !selectedOrg || selectedOrg === 'all' ? 'All organizations' : selectedOrg;

  const { data: systemHealth } = useQuery({
    queryKey: ['health-signals', 'system-dashboard'],
    queryFn: getSystemHealth,
    staleTime: 5 * 60 * 1000,
  });

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

      <div className={styles.customizeActions}>
        <Button type="button" size="sm" variant="default" onClick={() => setCatalogOpen(true)}>
          Add widgets
        </Button>
        <Button
          type="button"
          size="sm"
          variant="default"
          onClick={() => setCustomWidgetDialogOpen(true)}
        >
          Create custom widget
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
              <button className={styles.widgetAddBtn} onClick={() => setPersonaSelectorOpen(true)}>
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

      <CreateCustomWidgetDialog
        open={customWidgetDialogOpen}
        onClose={() => setCustomWidgetDialogOpen(false)}
        onCreated={handleCustomWidgetCreated}
      />
    </div>
  );
}
