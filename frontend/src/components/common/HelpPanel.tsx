import { useCallback, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { HelpContent } from './helpContent';
import styles from './HelpPanel.module.css';

interface HelpPanelProps {
  open: boolean;
  onClose: () => void;
  content: HelpContent | null;
}

export function HelpPanel({ open, onClose, content }: HelpPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<Element | null>(null);
  const titleId = useId();

  const handleEsc = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    },
    [onClose],
  );

  const handleFocusTrap = useCallback((event: KeyboardEvent) => {
    if (event.key !== 'Tab' || !panelRef.current) return;

    const focusableElements = panelRef.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
    );

    if (focusableElements.length === 0) return;

    const first = focusableElements[0];
    const last = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
      return;
    }

    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }, []);

  useEffect(() => {
    if (!open) {
      if (previousFocusRef.current instanceof HTMLElement) {
        previousFocusRef.current.focus();
      }
      return;
    }

    previousFocusRef.current = document.activeElement;
    document.addEventListener('keydown', handleEsc);
    document.addEventListener('keydown', handleFocusTrap);

    requestAnimationFrame(() => {
      panelRef.current?.querySelector<HTMLElement>('button, a[href]')?.focus();
    });

    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.removeEventListener('keydown', handleFocusTrap);
    };
  }, [open, handleEsc, handleFocusTrap]);

  if (!open || !content) {
    return null;
  }

  return createPortal(
    <div className={styles.overlay} onClick={onClose} data-testid="help-panel-overlay">
      <aside
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Contextual help</p>
            <h2 className={styles.title} id={titleId}>
              {content.title}
            </h2>
          </div>
          <button className={styles.closeButton} onClick={onClose} aria-label="Close help panel">
            ×
          </button>
        </div>

        <div className={styles.body}>
          <section className={styles.section}>
            <h3>About this page</h3>
            <p>{content.description}</p>
          </section>

          <section className={styles.section}>
            <h3>Key concepts</h3>
            <dl className={styles.definitionList}>
              {content.concepts.map((concept) => (
                <div key={concept.term} className={styles.definitionItem}>
                  <dt>{concept.term}</dt>
                  <dd>{concept.definition}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className={styles.section}>
            <h3>Common tasks</h3>
            <div className={styles.taskList}>
              {content.tasks.map((task) => (
                <div key={task.title} className={styles.taskCard}>
                  <h4>{task.title}</h4>
                  <ol>
                    {task.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <h3>Related pages</h3>
            <ul className={styles.relatedList}>
              {content.relatedPages.map((page) => (
                <li key={page.path}>
                  <a href={page.path}>{page.title}</a>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </aside>
    </div>,
    document.body,
  );
}
