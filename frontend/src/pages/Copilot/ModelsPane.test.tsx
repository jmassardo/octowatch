import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ModelsPane } from './ModelsPane';

vi.mock('react-router-dom', () => ({
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
  it('makes model usage bar rows clickable', async () => {
    renderPane();
    const gpt4oRow = (await screen.findByText('GPT-4o')).closest('[role="button"]');
    expect(gpt4oRow).toBeTruthy();
    expect(gpt4oRow).toHaveAttribute('tabIndex', '0');
  });

  it('opens model detail modal when clicking a model row', async () => {
    const user = userEvent.setup();
    renderPane();
    const gpt4oRow = (await screen.findByText('GPT-4o')).closest('[role="button"]')!;
    await user.click(gpt4oRow);
    expect(screen.getByText('GPT-4o — usage details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText(/42%/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Copilot Metrics API integration/)).toBeInTheDocument();
  });

  it('opens Claude model detail modal', async () => {
    const user = userEvent.setup();
    renderPane();
    const claudeRow = (await screen.findByText('Claude 3.7')).closest('[role="button"]')!;
    await user.click(claudeRow);
    expect(screen.getByText('Claude 3.7 — usage details')).toBeInTheDocument();
  });

  it('closes model modal via close button', async () => {
    const user = userEvent.setup();
    renderPane();
    const gpt4oRow = (await screen.findByText('GPT-4o')).closest('[role="button"]')!;
    await user.click(gpt4oRow);
    expect(screen.getByText('GPT-4o — usage details')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('GPT-4o — usage details')).not.toBeInTheDocument();
  });

  it('makes feature usage bar rows clickable', async () => {
    renderPane();
    const ideRow = (await screen.findByText('IDE completions')).closest('[role="button"]');
    expect(ideRow).toBeTruthy();
  });

  it('opens feature usage modal when clicking a feature row', async () => {
    const user = userEvent.setup();
    renderPane();
    const ideRow = (await screen.findByText('IDE completions')).closest('[role="button"]')!;
    await user.click(ideRow);
    expect(screen.getByText('IDE completions — usage details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText('142')).toBeInTheDocument();
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

  it('shows model details in modal', async () => {
    const user = userEvent.setup();
    renderPane();
    const gpt4oRow = (await screen.findByText('GPT-4o')).closest('[role="button"]')!;
    await user.click(gpt4oRow);
    expect(screen.getByText(/GPT-4o — usage details/)).toBeInTheDocument();
  });
});
