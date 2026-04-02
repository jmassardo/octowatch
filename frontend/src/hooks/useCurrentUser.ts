import { useQuery } from '@tanstack/react-query';
import { getMe } from '../api/auth';

export function useCurrentUser() {
  return useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    retry: false,
    staleTime: 60 * 1000, // re-validate after 1 min
    refetchOnWindowFocus: true, // detect invalidated sessions on tab re-focus
  });
}
