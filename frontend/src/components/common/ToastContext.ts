import { createContext } from 'react';
import type { ToastVariant } from './Toast';

export interface ShowToastOptions {
  /** Auto-dismiss duration in ms. Pass 0 to disable. Default 5000. */
  duration?: number;
}

export interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant, options?: ShowToastOptions) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);
