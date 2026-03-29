import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getFeatures, updateFeatures } from '../api/features';
import type { FeatureFlags } from '../api/features';

const DEFAULTS: FeatureFlags = {
  copilot_insights: false,
  velocity: true,
  dev_activity: true,
  org_health: true,
};

export function useFeatures() {
  const queryClient = useQueryClient();

  const { data: features, isLoading } = useQuery({
    queryKey: ['features'],
    queryFn: getFeatures,
    staleTime: 300_000, // 5 min cache
    placeholderData: DEFAULTS,
  });

  const toggleMutation = useMutation({
    mutationFn: (updates: Partial<FeatureFlags>) => updateFeatures(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features'] });
    },
  });

  return {
    features: features ?? DEFAULTS,
    isLoading,
    toggleFeature: (key: keyof FeatureFlags, enabled: boolean) =>
      toggleMutation.mutate({ [key]: enabled }),
    isToggling: toggleMutation.isPending,
  };
}
