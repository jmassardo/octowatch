import { Card } from '../primitives/Card';
import type { WidgetSize } from './WidgetRegistry';
import styles from './Widgets.module.css';

interface WidgetCardProps {
  readonly title: string;
  readonly description: string;
  readonly size: WidgetSize;
  readonly children: React.ReactNode;
  readonly draggable?: boolean;
  readonly isDragging?: boolean;
  readonly isDropTarget?: boolean;
  readonly onDragStart?: React.DragEventHandler<HTMLDivElement>;
  readonly onDragEnd?: React.DragEventHandler<HTMLDivElement>;
  readonly onDragOver?: React.DragEventHandler<HTMLDivElement>;
  readonly onDrop?: React.DragEventHandler<HTMLDivElement>;
  readonly onRemove: () => void;
  readonly onResize: () => void;
}

const NEXT_SIZE_LABEL: Record<WidgetSize, string> = {
  sm: 'Medium',
  md: 'Large',
  lg: 'Small',
};

export function WidgetCard({
  title,
  description,
  size,
  children,
  draggable,
  isDragging,
  isDropTarget,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
  onRemove,
  onResize,
}: WidgetCardProps) {
  return (
    <Card
      className={[
        styles.card,
        isDragging && styles.cardDragging,
        isDropTarget && styles.cardDropTarget,
      ]
        .filter(Boolean)
        .join(' ')}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <div className={styles.cardHeader}>
        <div className={styles.cardTitleBlock}>
          <span className={styles.cardTitle}>{title}</span>
          <span className={styles.cardDescription}>{description}</span>
        </div>
        <div className={styles.cardActions}>
          <button
            type="button"
            className={styles.handle}
            aria-label={`Drag ${title}`}
            title="Drag to reorder"
          >
            ⋮⋮
          </button>
          <button
            type="button"
            className={styles.iconButton}
            aria-label={`Remove ${title}`}
            title="Remove widget"
            onClick={onRemove}
          >
            ×
          </button>
        </div>
      </div>
      <div className={styles.cardBody}>{children}</div>
      <div className={styles.cardFooter}>
        <span className={styles.cardMeta}>Size: {size.toUpperCase()}</span>
        <button
          type="button"
          className={styles.resizeGrip}
          aria-label={`Resize ${title} to ${NEXT_SIZE_LABEL[size]}`}
          title={`Resize to ${NEXT_SIZE_LABEL[size]}`}
          onClick={onResize}
        >
          ⤢
        </button>
      </div>
    </Card>
  );
}
