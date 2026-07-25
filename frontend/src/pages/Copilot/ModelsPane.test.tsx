import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ModelsPane } from './ModelsPane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotModels: vi.fn().mockResolvedValue({
    models: [
      { model: 'GPT-4o', pct: 42, color: '#58a6ff' },
      { model: 'Claude 3.7', pct: 31, color: '#bc8cff' },
      { model: 'o3-mini', pct: 15, color: '#3fb950' },
      { model: 'Custom', pct: 8, color: '#d29922' },
      { model: 'GPT-4o-mini', pct: 4, color: '#8b949e' },
    ],
    features: [
      { feature: 'IDE completions', count: 142, color: '#58a6ff' },
      { feature: 'IDE chat', count: 98, color: '#bc8cff' },
      { feature: 'github.com chat', count: 61, color: '#3fb950' },
      { feature: 'PR summaries', count: 44, color: '#d29922' },
      { feature: 'CLI', count: 18, color: '#f85149' },
      { feature: 'Knowledge bases', count: 12, color: '#8b949e' },
    ],
    editors: [
      { name: 'VS Code', count: 112, pct: 79 },
      { name: 'JetBrains', count: 38, pct: 27 },
      { name: 'Neovim', count: 8, pct: 6 },
      { name: 'Xcode', count: 3, pct: 2 },
      { name: 'Other', count: 2, pct: 1 },
    ],
    time_series: {
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      models: { 'GPT-4o': [12, 15, 8], 'Claude 3.7': [5, 7, 9] },
      features: { 'IDE completions': [50, 55, 48], 'IDE chat': [20, 22, 25] },
    },
  }),
  getCopilotOverview: vi.fn().mockResolvedValue({
    acceptance_rate_days: ['2026-06-01', '2026-06-02'],
    acceptance_rate_values: [30, 32],
    acceptance_threshold: 25,
    languages: [
      { lang: 'TypeScript', pct: 38, color: '#3fb950' },
      { lang: 'Python', pct: 34, color: '#3fb950' },
    ],
    total_active_users: 100,
    total_engaged_users: 80,
    total_provisioned_seats: 120,
  }),
  getCopilotModelUsers: vi.fn().mockResolvedValue({
    users: [
      {
        login: 'user1',
        total_credits: 45.2,
        completions_credits: 20.1,
        chat_credits: 15.0,
        pr_credits: 8.1,
        other_credits: 2.0,
        days_active: 22,
        last_active: '2026-06-08',
      },
      {
        login: 'user2',
        total_credits: 32.5,
        completions_credits: 18.0,
        chat_credits: 10.5,
        pr_credits: 3.0,
        other_credits: 1.0,
        days_active: 18,
        last_active: '2026-06-07',
      },
    ],
    total_users: 2,
  }),
}));

function getDialog(): HTMLElement {
  return document.querySelector('.dialog')! as HTMLElement;
}

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ModelsPane />
    </QueryClientProvider>,
  );
}

describe('ModelsPane clickable stats', () => {
  it('renders donut charts for model and feature distribution', async () => {
    renderPane();
    expect(await screen.findByText('Model usage distribution')).toBeInTheDocument();
    expect(screen.getByText('Feature usage distribution')).toBeInTheDocument();
  });

  it('renders time series charts when data is available', async () => {
    renderPane();
    expect(await screen.findByText('Model usage trends (last 28 days)')).toBeInTheDocument();
    expect(screen.getByText('Feature usage trends (last 28 days)')).toBeInTheDocument();
  });

  it('renders acceptance rate by language section', async () => {
    renderPane();
    expect(await screen.findByText('Acceptance rate by language')).toBeInTheDocument();
    const tsRow = (await screen.findByText('TypeScript')).closest('[role="button"]');
    expect(tsRow).toBeTruthy();
    expect(tsRow).toHaveAttribute('tabIndex', '0');
  });

  it('opens language modal when clicking a language row', async () => {
    const user = userEvent.setup();
    renderPane();
    const tsRow = (await screen.findByText('TypeScript')).closest('[role="button"]')!;
    await user.click(tsRow);
    expect(screen.getByText('TypeScript — Acceptance rate details')).toBeInTheDocument();
    expect(screen.getByText(/acceptance rate of/)).toBeInTheDocument();
  });

  it('makes editor cards clickable', async () => {
    renderPane();
    const vsCodeWrapper = (await screen.findByText('VS Code')).closest('[role="button"]');
    expect(vsCodeWrapper).toBeTruthy();
    expect(vsCodeWrapper).toHaveAttribute('tabIndex', '0');
  });

  it('opens editor detail modal when clicking an editor card', async () => {
    const user = userEvent.setup();
    renderPane();
    const vsCodeWrapper = (await screen.findByText('VS Code')).closest('[role="button"]')!;
    await user.click(vsCodeWrapper);
    expect(screen.getByText('VS Code — editor details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText('112')).toBeInTheDocument();
    expect(within(dialog).getByText(/User distribution by editor/)).toBeInTheDocument();
  });

  it('opens JetBrains editor modal', async () => {
    const user = userEvent.setup();
    renderPane();
    const jbWrapper = (await screen.findByText('JetBrains')).closest('[role="button"]')!;
    await user.click(jbWrapper);
    expect(screen.getByText('JetBrains — editor details')).toBeInTheDocument();
  });

  it('closes editor modal via close button', async () => {
    const user = userEvent.setup();
    renderPane();
    const vsCodeWrapper = (await screen.findByText('VS Code')).closest('[role="button"]')!;
    await user.click(vsCodeWrapper);
    expect(screen.getByText('VS Code — editor details')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('VS Code — editor details')).not.toBeInTheDocument();
  });

  it('renders editor breakdown section', async () => {
    renderPane();
    expect(await screen.findByText('Editor breakdown')).toBeInTheDocument();
  });

  it('opens language modal for different languages', async () => {
    const user = userEvent.setup();
    renderPane();
    const pyRow = (await screen.findByText('Python')).closest('[role="button"]')!;
    await user.click(pyRow);
    expect(screen.getByText('Python — Acceptance rate details')).toBeInTheDocument();
  });

  it('renders donut chart aria labels for accessibility', async () => {
    renderPane();
    await screen.findByText('Model usage distribution');
    const figures = screen.getAllByRole('figure');
    expect(figures.length).toBeGreaterThanOrEqual(2);
  });
});
