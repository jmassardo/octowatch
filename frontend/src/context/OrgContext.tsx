import { useState } from 'react';
import { OrgContext } from './OrgContextValue';

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const [selectedOrg, setSelectedOrg] = useState('');
  return (
    <OrgContext.Provider value={{ selectedOrg, setSelectedOrg }}>{children}</OrgContext.Provider>
  );
}
