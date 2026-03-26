import { createContext } from 'react';

export interface OrgContextValue {
  selectedOrg: string;
  setSelectedOrg: (org: string) => void;
}

export const OrgContext = createContext<OrgContextValue>({
  selectedOrg: '',
  setSelectedOrg: () => {},
});
