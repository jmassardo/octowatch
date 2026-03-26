import { useContext } from 'react';
import { OrgContext } from '../context/OrgContextValue';

export const useOrg = () => useContext(OrgContext);
