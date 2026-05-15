import { useMemo, useState } from 'react';
import { Button } from '../primitives/Button';
import { Drawer } from '../primitives/Drawer';
import type { CatalogWidget } from '../../api/dashboardConfig';
import styles from './WidgetCatalog.module.css';

const CATEGORY_LABELS: Record<string, string> = {
  security: 'Security',
  operations: 'Operations',
  activity: 'Activity',
  copilot: 'Copilot',
};

interface WidgetCatalogProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly widgets: readonly CatalogWidget[];
  readonly activeWidgetIds: ReadonlySet<string>;
  readonly onAdd: (widgetId: string) => void;
  readonly onRemove: (widgetId: string) => void;
}

export function WidgetCatalog({
  open,
  onClose,
  widgets,
  activeWidgetIds,
  onAdd,
  onRemove,
}: WidgetCatalogProps) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return widgets;
    const q = search.toLowerCase();
    return widgets.filter(
      (w) =>
        w.title.toLowerCase().includes(q) ||
        w.description.toLowerCase().includes(q) ||
        w.category.toLowerCase().includes(q),
    );
  }, [widgets, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, CatalogWidget[]>();
    for (const w of filtered) {
      const existing = map.get(w.category);
      if (existing) {
        existing.push(w);
      } else {
        map.set(w.category, [w]);
      }
    }
    return map;
  }, [filtered]);

  return (
    <Drawer open={open} onClose={onClose} title="Widget catalog">
      <div className={styles.body}>
        <input
          type="search"
          className={styles.search}
          placeholder="Search widgets…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search widgets"
        />

        {filtered.length === 0 && <p className={styles.empty}>No widgets match your search.</p>}

        {Array.from(grouped.entries()).map(([category, items]) => (
          <section key={category} className={styles.section}>
            <h3 className={styles.categoryTitle}>{CATEGORY_LABELS[category] ?? category}</h3>
            <div className={styles.list}>
              {items.map((widget) => {
                const isActive = activeWidgetIds.has(widget.id);
                return (
                  <div key={widget.id} className={styles.item}>
                    <div className={styles.itemInfo}>
                      <div className={styles.itemTitle}>{widget.title}</div>
                      <div className={styles.itemDesc}>{widget.description}</div>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant={isActive ? 'default' : 'primary'}
                      onClick={() => (isActive ? onRemove(widget.id) : onAdd(widget.id))}
                    >
                      {isActive ? 'Remove' : 'Add'}
                    </Button>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </Drawer>
  );
}
