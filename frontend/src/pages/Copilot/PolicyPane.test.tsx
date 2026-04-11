import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PolicyPane } from './PolicyPane';

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotPolicyChanges: vi.fn().mockResolvedValue({
    timeline: [
      {
        id: 1,
        action: 'copilot.cfb_enabled',
        actor: 'admin-user',
        timestamp: '2024-03-15T10:30:00Z',
        org: 'acme',
        description: 'Copilot for Business enabled',
        old_value: null,
        new_value: 'enabled',
      },
      {
        id: 2,
        action: 'copilot.content_exclusion_updated',
        actor: 'security-admin',
        timestamp: '2024-03-10T08:00:00Z',
        org: 'acme',
        description: 'Content exclusion patterns updated',
        old_value: '*.env',
        new_value: '*.env,*.secret',
      },
    ],
    total_changes: 2,
  }),
}));

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PolicyPane />
    </QueryClientProvider>,
  );
}

describe('PolicyPane', () => {
  it('shows total policy changes count', async () => {
    renderPane();
    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(screen.getByText('Total Policy Changes')).toBeInTheDocument();
  });

  it('renders timeline events', async () => {
    renderPane();
    expect(await screen.findByText('Copilot for Business enabled')).toBeInTheDocument();
    expect(screen.getByText('Content exclusion patterns updated')).toBeInTheDocument();
  });

  it('shows actor information', async () => {
    renderPane();
    expect(await screen.findByText('admin-user')).toBeInTheDocument();
    expect(screen.getByText('security-admin')).toBeInTheDocument();
  });

  it('shows action labels', async () => {
    renderPane();
    expect(await screen.findByText('copilot.cfb_enabled')).toBeInTheDocument();
    expect(screen.getByText('copilot.content_exclusion_updated')).toBeInTheDocument();
  });

  it('shows old and new values for policy changes', async () => {
    renderPane();
    expect(await screen.findByText('enabled')).toBeInTheDocument();
    expect(screen.getByText('*.env')).toBeInTheDocument();
    expect(screen.getByText('*.env,*.secret')).toBeInTheDocument();
  });
});
