import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthGuard } from './AuthGuard';
import type { ReactNode } from 'react';

vi.mock('../../hooks/useCurrentUser');
vi.mock('../../api/setup', () => ({
  getSetupStatus: vi.fn().mockResolvedValue({ setup_required: false }),
}));

import { useCurrentUser } from '../../hooks/useCurrentUser';

const mockUseCurrentUser = vi.mocked(useCurrentUser);

function renderAuthGuard(children: ReactNode, route = '/dashboard') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/dashboard" element={<AuthGuard>{children}</AuthGuard>} />
          <Route path="/login" element={<p>Login page</p>} />
          <Route path="/setup" element={<p>Setup page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AuthGuard', () => {
  beforeEach(() => {
    mockUseCurrentUser.mockReset();
  });

  it('shows spinner while loading', () => {
    mockUseCurrentUser.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderAuthGuard(<p>Protected content</p>);

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
    const spinner = document.querySelector('.spinner');
    expect(spinner).toBeInTheDocument();
  });

  it('renders children when authenticated', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: {
        github_login: 'testuser',
        github_id: 123,
        roles: ['admin'],
        scoped_orgs: [],
        scoped_repos: [],
        scope_type: 'all',
        session_expires_at: '2025-12-31T00:00:00Z',
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderAuthGuard(<p>Protected content</p>);

    expect(await screen.findByText('Protected content')).toBeInTheDocument();
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
  });

  it('redirects to /login when an error occurs', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderAuthGuard(<p>Protected content</p>);

    expect(await screen.findByText('Login page')).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('redirects to /login when user data is undefined', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderAuthGuard(<p>Protected content</p>);

    expect(await screen.findByText('Login page')).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });
});
