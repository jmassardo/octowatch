import { createContext, useContext } from 'react';
import type { HotkeyBinding } from '../hooks/useHotkeys';

export interface HotkeyContextValue {
  register: (binding: HotkeyBinding) => number;
  unregister: (id: number) => void;
  getAll: () => HotkeyBinding[];
}

export const HotkeyContext = createContext<HotkeyContextValue | null>(null);

export function useHotkeyContext(): HotkeyContextValue {
  const ctx = useContext(HotkeyContext);
  if (!ctx) {
    throw new Error('useHotkeyContext must be used within a HotkeyProvider');
  }
  return ctx;
}
