import { useQuery } from '@tanstack/react-query';
import { getMe } from '../api/auth';

export function useCurrentUser() {
  return useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}
