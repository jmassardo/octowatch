import { useQuery } from '@tanstack/react-query';
import { getOrgConfig } from '../api/orgConfig';
import { useOrg } from './useOrg';

const COST_PER_SEAT_DEFAULT = 19;

/**
 * Fetch per-org configuration from the API.
 *
 * Returns `costPerSeat` with a fallback to the global default of 19
 * when no org is selected or the API returns null.
 */
export function useOrgConfig() {
  const { selectedOrg } = useOrg();

  const { data, isLoading, isError } = useQuery({
    queryKey: ['org-config', selectedOrg],
    queryFn: () => getOrgConfig(selectedOrg),
    enabled: selectedOrg !== '',
    staleTime: 60_000,
  });

  const costPerSeat = data?.copilot_cost_per_seat ?? COST_PER_SEAT_DEFAULT;

  return { costPerSeat, isLoading, isError, orgConfig: data };
}
