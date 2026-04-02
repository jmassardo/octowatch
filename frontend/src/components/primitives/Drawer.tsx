import { useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import styles from './Drawer.module.css';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  /** An element id used for aria-labelledby. Falls back to title text. */
  titleId?: string;
  children: React.ReactNode;
}

/**
 * A right-side slide-out panel (drawer) with backdrop overlay.
 *
 * - Closes on Escape key press
 * - Closes when clicking outside the panel (on the backdrop)
 * - Traps focus inside the panel while open
 * - Full-width on mobile / small viewports
 * - Uses `role="dialog"` and `aria-labelledby` for accessibility
 */
export function Drawer({ open, onClose, title, titleId, children }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<Element | null>(null);

  const handleEsc = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  // Focus trap: keep focus inside the panel
  const handleFocusTrap = useCallback((e: KeyboardEvent) => {
    if (e.key !== 'Tab' || !panelRef.current) return;

    const focusableEls = panelRef.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
    );
    if (focusableEls.length === 0) return;

    const first = focusableEls[0]!;
    const last = focusableEls[focusableEls.length - 1]!;

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }, []);

  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement;
      document.addEventListener('keydown', handleEsc);
      document.addEventListener('keydown', handleFocusTrap);

      // Focus the close button (first focusable element) when opened
      requestAnimationFrame(() => {
        const closeBtn = panelRef.current?.querySelector<HTMLElement>('button');
        closeBtn?.focus();
      });

      return () => {
        document.removeEventListener('keydown', handleEsc);
        document.removeEventListener('keydown', handleFocusTrap);
      };
    } else {
      // Restore focus to previously focused element on close
      if (previousFocusRef.current instanceof HTMLElement) {
        previousFocusRef.current.focus();
      }
    }
  }, [open, handleEsc, handleFocusTrap]);

  if (!open) return null;

  const labelId = titleId ?? (title ? 'drawer-title' : undefined);

  return createPortal(
    <>
      <div className={styles.backdrop} onClick={onClose} data-testid="drawer-backdrop" />
      <div
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        data-testid="drawer-panel"
      >
        <div className={styles.header}>
          <span className={styles.title} id={labelId}>
            {title}
          </span>
          <button className={styles.close} onClick={onClose} aria-label="Close">
            &#215;
          </button>
        </div>
        <div className={styles.body}>{children}</div>
      </div>
    </>,
    document.body,
  );
}
