import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('../api/orgConfig');
vi.mock('./useOrg');

import { getOrgConfig } from '../api/orgConfig';
import { useOrg } from './useOrg';
import { useOrgConfig } from './useOrgConfig';

const mockGetOrgConfig = vi.mocked(getOrgConfig);
const mockUseOrg = vi.mocked(useOrg);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useOrgConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns default costPerSeat (19) when no org is selected', () => {
    mockUseOrg.mockReturnValue({ selectedOrg: '', setSelectedOrg: vi.fn() });

    const { result } = renderHook(() => useOrgConfig(), {
      wrapper: createWrapper(),
    });

    expect(result.current.costPerSeat).toBe(19);
    expect(mockGetOrgConfig).not.toHaveBeenCalled();
  });

  it('fetches org config and returns custom costPerSeat', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg: vi.fn() });
    mockGetOrgConfig.mockResolvedValue({
      org_slug: 'my-org',
      copilot_cost_per_seat: 39,
    });

    const { result } = renderHook(() => useOrgConfig(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.costPerSeat).toBe(39);
    });

    expect(mockGetOrgConfig).toHaveBeenCalledWith('my-org');
  });

  it('returns default when API returns null costPerSeat', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg: vi.fn() });
    mockGetOrgConfig.mockResolvedValue({
      org_slug: 'my-org',
      copilot_cost_per_seat: 19,
    });

    const { result } = renderHook(() => useOrgConfig(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.costPerSeat).toBe(19);
    });
  });

  it('returns default costPerSeat on error', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg: vi.fn() });
    mockGetOrgConfig.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useOrgConfig(), {
      wrapper: createWrapper(),
    });

    // Should return default while loading/error
    expect(result.current.costPerSeat).toBe(19);
  });
});
