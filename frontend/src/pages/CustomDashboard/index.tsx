import { useCallback, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Responsive, type LayoutItem, type Layout, verticalCompactor } from 'react-grid-layout';
import {
  getDashboardConfig,
  updateDashboardConfig,
  getWidgetCatalog,
  type WidgetLayoutItem as ApiLayoutItem,
  type CatalogWidget,
} from '../../api/dashboardConfig';
import { getWidgetDefinition } from '../../components/widgets/WidgetRegistry';
import { PersonaSelector } from '../../components/widgets/PersonaSelector';
import { WidgetCatalog } from '../../components/widgets/WidgetCatalog';
import { PERSONA_WIDGET_PRESETS } from '../../components/widgets/WidgetRegistry';
import type { DashboardPersona } from '../../components/widgets/WidgetRegistry';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './CustomDashboard.module.css';
import 'react-grid-layout/css/styles.css';

const ResponsiveGridLayout = Responsive;

/** Convert API layout items to react-grid-layout format. */
function toGridLayouts(items: readonly ApiLayoutItem[]): LayoutItem[] {
  return items.map((item) => ({
    i: item.widget_id,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
    minW: 2,
    minH: 2,
  }));
}

/** Convert react-grid-layout items back to API format. */
function fromGridLayouts(layouts: Layout): ApiLayoutItem[] {
  return layouts.map((l) => ({
    widget_id: l.i,
    x: l.x,
    y: l.y,
    w: l.w,
    h: l.h,
  }));
}

/** Convert persona preset (sm/md/lg) to grid layout items with proper x/y/w/h. */
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

export function CustomDashboardPage() {
  const queryClient = useQueryClient();
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [personaDismissed, setPersonaDismissed] = useState(false);
  const [personaForced, setPersonaForced] = useState(false);

  // Fetch user's dashboard config
  const configQuery = useQuery({
    queryKey: ['dashboard-config'],
    queryFn: getDashboardConfig,
    staleTime: 30_000,
  });

  // Fetch the widget catalog
  const catalogQuery = useQuery({
    queryKey: ['dashboard-widgets'],
    queryFn: getWidgetCatalog,
    staleTime: 300_000,
  });

  const catalogWidgets = catalogQuery.data?.widgets ?? [];

  // Show persona selector on first visit (no persona set) or when forced open
  const isFirstVisit =
    configQuery.data !== undefined &&
    !configQuery.data.persona &&
    configQuery.data.layout.length === 0;
  const showPersona = personaForced || (isFirstVisit && !personaDismissed);

  // Mutation to save layout
  const saveMutation = useMutation({
    mutationFn: updateDashboardConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(['dashboard-config'], data);
    },
  });

  // Current layout from server
  const apiLayout: readonly ApiLayoutItem[] = configQuery.data?.layout ?? [];
  const gridLayouts = useMemo(() => toGridLayouts(apiLayout), [apiLayout]);

  // Set of active widget IDs
  const activeWidgetIds = useMemo(
    () => new Set(apiLayout.map((item) => item.widget_id)),
    [apiLayout],
  );

  // Handle grid layout change
  const handleLayoutChange = useCallback(
    (newLayout: Layout) => {
      // Filter to only widgets we have in our current layout
      const validIds = new Set(apiLayout.map((item) => item.widget_id));
      const filtered = newLayout.filter((l) => validIds.has(l.i));
      const nextLayout = fromGridLayouts(filtered);

      saveMutation.mutate({
        layout: nextLayout,
        persona: configQuery.data?.persona ?? '',
      });
    },
    [apiLayout, saveMutation, configQuery.data?.persona],
  );

  // Add a widget
  const handleAddWidget = useCallback(
    (widgetId: string) => {
      if (activeWidgetIds.has(widgetId)) return;

      const cw = catalogWidgets.find((w) => w.id === widgetId);
      const newItem: ApiLayoutItem = {
        widget_id: widgetId,
        x: 0,
        y: Infinity, // react-grid-layout places it at the bottom
        w: cw?.default_w ?? 4,
        h: cw?.default_h ?? 3,
      };

      saveMutation.mutate({
        layout: [...apiLayout, newItem],
        persona: configQuery.data?.persona ?? '',
      });
    },
    [activeWidgetIds, apiLayout, catalogWidgets, saveMutation, configQuery.data?.persona],
  );

  // Remove a widget
  const handleRemoveWidget = useCallback(
    (widgetId: string) => {
      saveMutation.mutate({
        layout: apiLayout.filter((item) => item.widget_id !== widgetId),
        persona: configQuery.data?.persona ?? '',
      });
    },
    [apiLayout, saveMutation, configQuery.data?.persona],
  );

  // Persona selection
  const handlePersonaSelect = useCallback(
    (personaId: string) => {
      const presetIds = PERSONA_WIDGET_PRESETS[personaId as DashboardPersona];
      if (!presetIds) return;

      const layout = presetToApiLayout(presetIds, catalogWidgets);
      saveMutation.mutate({ layout, persona: personaId });
      setPersonaForced(false);
      setPersonaDismissed(true);
    },
    [catalogWidgets, saveMutation],
  );

  const handlePersonaSkip = useCallback(() => {
    setPersonaDismissed(true);
    setPersonaForced(false);
  }, []);

  if (configQuery.isLoading || catalogQuery.isLoading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <Spinner />
      </div>
    );
  }

  if (configQuery.isError) {
    return (
      <ErrorBanner
        message="Failed to load dashboard configuration"
        onRetry={() => void configQuery.refetch()}
      />
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="Custom Dashboard"
        description="Drag, resize, and add widgets to build your ideal view."
      />

      <div className={styles.toolbar}>
        <Button type="button" variant="primary" onClick={() => setCatalogOpen(true)}>
          Add widgets
        </Button>
        <Button type="button" variant="default" onClick={() => setPersonaForced(true)}>
          Change persona
        </Button>
        {saveMutation.isPending && <span className={styles.saving}>Saving…</span>}
      </div>

      {apiLayout.length === 0 ? (
        <div className={styles.emptyState}>
          <h3>Your dashboard is empty</h3>
          <p>Choose a persona for a recommended layout, or add widgets manually.</p>
          <div className={styles.emptyActions}>
            <Button type="button" variant="primary" onClick={() => setPersonaForced(true)}>
              Choose persona
            </Button>
            <Button type="button" variant="default" onClick={() => setCatalogOpen(true)}>
              Browse widgets
            </Button>
          </div>
        </div>
      ) : (
        <ResponsiveGridLayout
          className={styles.grid}
          width={1200}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480 }}
          cols={{ lg: 12, md: 12, sm: 6, xs: 4 }}
          rowHeight={80}
          layouts={{ lg: gridLayouts }}
          onLayoutChange={handleLayoutChange}
          dragConfig={{ enabled: true, handle: `.${styles.dragHandle}` }}
          resizeConfig={{ enabled: true }}
          compactor={verticalCompactor}
        >
          {apiLayout.map((item) => {
            const def = getWidgetDefinition(item.widget_id);
            const WidgetComponent = def?.component;

            return (
              <div key={item.widget_id} className={styles.widgetWrapper}>
                <div className={styles.widgetHeader}>
                  <span className={styles.dragHandle} title="Drag to reorder">
                    ⋮⋮
                  </span>
                  <span className={styles.widgetTitle}>{def?.title ?? item.widget_id}</span>
                  <button
                    type="button"
                    className={styles.removeBtn}
                    onClick={() => handleRemoveWidget(item.widget_id)}
                    aria-label={`Remove ${def?.title ?? item.widget_id}`}
                    title="Remove widget"
                  >
                    ×
                  </button>
                </div>
                <div className={styles.widgetBody}>
                  {WidgetComponent ? <WidgetComponent /> : <p>Widget not found</p>}
                </div>
              </div>
            );
          })}
        </ResponsiveGridLayout>
      )}

      <WidgetCatalog
        open={catalogOpen}
        onClose={() => setCatalogOpen(false)}
        widgets={catalogWidgets}
        activeWidgetIds={activeWidgetIds}
        onAdd={handleAddWidget}
        onRemove={handleRemoveWidget}
      />

      <PersonaSelector
        open={showPersona}
        onSelect={handlePersonaSelect}
        onSkip={handlePersonaSkip}
      />
    </div>
  );
}
