import { useCallback, useMemo } from 'react';
import {
  getBindings,
  registerBinding,
  unregisterBinding,
  type HotkeyBinding,
} from '../hooks/useHotkeys';
import { HotkeyContext, type HotkeyContextValue } from './HotkeyContext';

export function HotkeyProvider({ children }: { children: React.ReactNode }) {
  const register = useCallback((binding: HotkeyBinding) => registerBinding(binding), []);
  const unregister = useCallback((id: number) => unregisterBinding(id), []);
  const getAll = useCallback(() => getBindings(), []);

  const value = useMemo<HotkeyContextValue>(
    () => ({ register, unregister, getAll }),
    [register, unregister, getAll],
  );

  return <HotkeyContext.Provider value={value}>{children}</HotkeyContext.Provider>;
}
