import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router';
import type { ReactElement, ReactNode } from 'react';
import { ToastProvider } from '../components/common/ToastProvider';
import { OrgProvider } from '../context/OrgContext';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'> & { route?: string; routePath?: string },
) {
  const queryClient = createTestQueryClient();
  const { route = '/', routePath, ...renderOptions } = options ?? {};

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <OrgProvider>
          <ToastProvider>
            <MemoryRouter initialEntries={[route]}>
              {routePath ? (
                <Routes>
                  <Route path={routePath} element={children} />
                </Routes>
              ) : (
                children
              )}
            </MemoryRouter>
          </ToastProvider>
        </OrgProvider>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...renderOptions });
}
