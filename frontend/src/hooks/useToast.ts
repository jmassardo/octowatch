import { useContext } from 'react';
import { ToastContext } from '../components/common/ToastContext';
import type { ToastContextValue } from '../components/common/ToastContext';

/**
 * Access the toast notification system.
 *
 * @returns `{ showToast(message, variant?, options?) }` for firing toasts.
 * @throws Error if used outside of `<ToastProvider>`.
 *
 * @example
 * ```tsx
 * const { showToast } = useToast();
 * showToast('Settings saved', 'success');
 * showToast('Something went wrong', 'error', { duration: 8000 });
 * ```
 */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a <ToastProvider>');
  }
  return ctx;
}
