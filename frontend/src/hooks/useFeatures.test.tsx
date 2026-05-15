import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('../api/features');

import { getFeatures, updateFeatures } from '../api/features';
import { useFeatures } from './useFeatures';

const mockGetFeatures = vi.mocked(getFeatures);
const mockUpdateFeatures = vi.mocked(updateFeatures);

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

describe('useFeatures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns defaults as placeholderData before fetch completes', () => {
    mockGetFeatures.mockReturnValue(new Promise(() => {})); // never resolves

    const { result } = renderHook(() => useFeatures(), {
      wrapper: createWrapper(),
    });

    expect(result.current.features).toEqual({
      copilot_insights: true,
      velocity: true,
      dev_activity: true,
      org_health: true,
    });
    // With placeholderData, isLoading is false even before the query resolves
    // because placeholderData provides immediate data
    expect(result.current.isLoading).toBe(false);
  });

  it('returns fetched features after query resolves', async () => {
    mockGetFeatures.mockResolvedValue({
      copilot_insights: true,
      velocity: false,
      dev_activity: true,
      org_health: true,
    });

    const { result } = renderHook(() => useFeatures(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.features.velocity).toBe(false);
    });

    expect(result.current.features.copilot_insights).toBe(true);
    expect(result.current.isLoading).toBe(false);
  });

  it('returns defaults when fetch fails', async () => {
    mockGetFeatures.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useFeatures(), {
      wrapper: createWrapper(),
    });

    // Should still have defaults
    expect(result.current.features.copilot_insights).toBe(true);
    expect(result.current.features.velocity).toBe(true);
  });

  it('calls updateFeatures when toggleFeature is invoked', async () => {
    mockGetFeatures.mockResolvedValue({
      copilot_insights: false,
      velocity: true,
      dev_activity: true,
      org_health: true,
    });
    mockUpdateFeatures.mockResolvedValue({ copilot_insights: true });

    const { result } = renderHook(() => useFeatures(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.toggleFeature('copilot_insights', true);
    });

    await waitFor(() => {
      expect(mockUpdateFeatures).toHaveBeenCalledWith({ copilot_insights: true });
    });
  });

  it('isToggling is true during mutation', async () => {
    mockGetFeatures.mockResolvedValue({
      copilot_insights: false,
      velocity: true,
      dev_activity: true,
      org_health: true,
    });

    let resolveUpdate: (value: { copilot_insights: boolean }) => void;
    mockUpdateFeatures.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      }),
    );

    const { result } = renderHook(() => useFeatures(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.toggleFeature('copilot_insights', true);
    });

    await waitFor(() => {
      expect(result.current.isToggling).toBe(true);
    });

    // Resolve the mutation
    await act(async () => {
      resolveUpdate!({ copilot_insights: true });
    });

    await waitFor(() => {
      expect(result.current.isToggling).toBe(false);
    });
  });
});
