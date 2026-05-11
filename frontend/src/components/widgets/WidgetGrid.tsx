import { useMemo, useState } from 'react';
import { Button } from '../primitives/Button';
import { Modal } from '../primitives/Modal';
import { WidgetCard } from './WidgetCard';
import {
  WIDGET_CATEGORY_LABELS,
  WIDGET_REGISTRY,
  type WidgetDefinition,
  type WidgetLayoutItem,
  type WidgetSize,
} from './WidgetRegistry';
import styles from './Widgets.module.css';

interface WidgetGridProps {
  readonly layout: readonly WidgetLayoutItem[];
  readonly onChange: (layout: WidgetLayoutItem[]) => void;
  readonly definitions?: readonly WidgetDefinition[];
}

const NEXT_SIZE: Record<WidgetSize, WidgetSize> = {
  sm: 'md',
  md: 'lg',
  lg: 'sm',
};

export function WidgetGrid({ layout, onChange, definitions = WIDGET_REGISTRY }: WidgetGridProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draggedWidgetId, setDraggedWidgetId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);

  const visibleWidgets = useMemo(
    () =>
      layout.flatMap((item) => {
        const definition = definitions.find((candidate) => candidate.id === item.id);
        return definition ? [{ item, definition }] : [];
      }),
    [definitions, layout],
  );

  const categories = useMemo(
    () =>
      Object.entries(WIDGET_CATEGORY_LABELS).map(([category, label]) => ({
        category,
        label,
        widgets: definitions.filter((widget) => widget.category === category),
      })),
    [definitions],
  );

  function updateWidget(
    widgetId: string,
    updater: (item: WidgetLayoutItem) => WidgetLayoutItem | null,
  ) {
    onChange(
      layout.flatMap((item) => {
        if (item.id !== widgetId) return [item];
        const next = updater(item);
        return next ? [next] : [];
      }),
    );
  }

  function addWidget(widgetId: string) {
    const widget = definitions.find((candidate) => candidate.id === widgetId);
    if (!widget || layout.some((item) => item.id === widgetId)) return;
    onChange([...layout, { id: widget.id, size: widget.defaultSize }]);
  }

  function removeWidget(widgetId: string) {
    onChange(layout.filter((item) => item.id !== widgetId));
  }

  function moveWidget(sourceId: string, targetId: string) {
    if (sourceId === targetId) return;

    const sourceIndex = layout.findIndex((item) => item.id === sourceId);
    const targetIndex = layout.findIndex((item) => item.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;

    const next = [...layout];
    const [moved] = next.splice(sourceIndex, 1);
    next.splice(targetIndex, 0, moved);
    onChange(next);
  }

  return (
    <div className={styles.gridShell}>
      <div className={styles.gridToolbar}>
        <div>
          <h2>Unified widget dashboard</h2>
          <p>
            Curate the signals that matter most, then drag, resize, and remove widgets as your focus
            shifts.
          </p>
        </div>
        <Button type="button" variant="primary" onClick={() => setPickerOpen(true)}>
          Customize
        </Button>
      </div>

      {visibleWidgets.length === 0 ? (
        <div className={styles.emptyState}>
          <h3>Build your dashboard</h3>
          <p>Start with recommended widgets or pick the signals you want to monitor every day.</p>
          <Button type="button" variant="primary" onClick={() => setPickerOpen(true)}>
            Add widgets
          </Button>
        </div>
      ) : (
        <div className={styles.grid}>
          {visibleWidgets.map(({ item, definition }) => {
            const WidgetComponent = definition.component;
            return (
              <div
                key={item.id}
                className={[
                  styles.gridItem,
                  styles[`size${item.size.charAt(0).toUpperCase()}${item.size.slice(1)}`],
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                <WidgetCard
                  title={definition.title}
                  description={definition.description}
                  size={item.size}
                  draggable
                  isDragging={draggedWidgetId === item.id}
                  isDropTarget={dropTargetId === item.id}
                  onDragStart={(event) => {
                    event.dataTransfer.effectAllowed = 'move';
                    event.dataTransfer.setData('text/plain', item.id);
                    setDraggedWidgetId(item.id);
                  }}
                  onDragEnd={() => {
                    setDraggedWidgetId(null);
                    setDropTargetId(null);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = 'move';
                    if (dropTargetId !== item.id) setDropTargetId(item.id);
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    const sourceId = event.dataTransfer.getData('text/plain') || draggedWidgetId;
                    if (sourceId) moveWidget(sourceId, item.id);
                    setDraggedWidgetId(null);
                    setDropTargetId(null);
                  }}
                  onRemove={() => removeWidget(item.id)}
                  onResize={() =>
                    updateWidget(item.id, (current) => ({
                      ...current,
                      size: NEXT_SIZE[current.size],
                    }))
                  }
                >
                  <WidgetComponent />
                </WidgetCard>
              </div>
            );
          })}
        </div>
      )}

      <Modal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        title="Customize dashboard widgets"
        width={860}
      >
        <div className={styles.pickerBody}>
          {categories.map(({ category, label, widgets }) => (
            <section key={category} className={styles.categorySection}>
              <h3 className={styles.categoryTitle}>{label}</h3>
              <div className={styles.pickerGrid}>
                {widgets.map((widget) => {
                  const selected = layout.some((item) => item.id === widget.id);
                  return (
                    <div
                      key={widget.id}
                      className={[styles.pickerOption, selected && styles.pickerSelected]
                        .filter(Boolean)
                        .join(' ')}
                    >
                      <div className={styles.pickerHeader}>
                        <div>
                          <div className={styles.pickerTitle}>{widget.title}</div>
                          <div className={styles.pickerDescription}>{widget.description}</div>
                        </div>
                        <span className={styles.badge}>{widget.defaultSize}</span>
                      </div>
                      <div className={styles.toggleRow}>
                        <span className={styles.muted}>
                          {selected ? 'Shown on dashboard' : 'Not added yet'}
                        </span>
                        <Button
                          type="button"
                          size="sm"
                          variant={selected ? 'default' : 'primary'}
                          onClick={() =>
                            selected ? removeWidget(widget.id) : addWidget(widget.id)
                          }
                        >
                          {selected ? 'Remove' : 'Add'}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </Modal>
    </div>
  );
}
