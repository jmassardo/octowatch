import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Toast } from './Toast';
import type { ToastItem, ToastVariant } from './Toast';
import { ToastContext } from './ToastContext';
import type { ShowToastOptions } from './ToastContext';
import styles from './Toast.module.css';

/** Maximum number of visible toasts. Older ones are evicted FIFO. */
const MAX_VISIBLE = 3;
/** Default auto-dismiss duration in milliseconds. */
const DEFAULT_DURATION_MS = 5000;

let nextId = 0;
function generateId(): string {
  nextId += 1;
  return `toast-${nextId}`;
}

/**
 * ToastProvider — renders up to {@link MAX_VISIBLE} toast notifications
 * and exposes `showToast` via React context.
 *
 * Wrap your app root with this provider and consume via `useToast()`.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const showToast = useCallback(
    (message: string, variant: ToastVariant = 'info', options?: ShowToastOptions) => {
      const duration = options?.duration ?? DEFAULT_DURATION_MS;
      const id = generateId();
      const item: ToastItem = { id, message, variant, duration };

      setToasts((prev) => {
        const next = [...prev, item];
        return next.length > MAX_VISIBLE ? next.slice(next.length - MAX_VISIBLE) : next;
      });

      if (duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration);
        timersRef.current.set(id, timer);
      }
    },
    [dismiss],
  );

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setToasts((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last) {
            const timer = timersRef.current.get(last.id);
            if (timer) {
              clearTimeout(timer);
              timersRef.current.delete(last.id);
            }
          }
          return prev.slice(0, -1);
        });
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={styles.container} aria-label="Notifications">
        {toasts.map((t) => (
          <Toast key={t.id} item={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
