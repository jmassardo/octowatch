import { Navigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { getSetupStatus } from '../../api/setup';
import { Spinner } from '../primitives/Spinner';

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { data: setupStatus, isLoading: setupLoading } = useQuery({
    queryKey: ['setup', 'status'],
    queryFn: getSetupStatus,
    staleTime: 60_000,
    retry: false,
  });

  const { data: user, isLoading, isError } = useCurrentUser();

  if (setupLoading || isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <Spinner size={32} />
      </div>
    );
  }

  if (setupStatus?.setup_required) {
    return <Navigate to="/setup" replace />;
  }

  if (isError || !user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
