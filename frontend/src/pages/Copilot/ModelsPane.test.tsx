import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelsPane } from './ModelsPane';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

function getDialog(): HTMLElement {
  return document.querySelector('.dialog')! as HTMLElement;
}

describe('ModelsPane clickable stats', () => {
  it('makes model usage bar rows clickable', () => {
    render(<ModelsPane />);
    const gpt4oRow = screen.getByText('GPT-4o').closest('[role="button"]');
    expect(gpt4oRow).toBeTruthy();
    expect(gpt4oRow).toHaveAttribute('tabIndex', '0');
  });

  it('opens model detail modal when clicking a model row', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const gpt4oRow = screen.getByText('GPT-4o').closest('[role="button"]')!;
    await user.click(gpt4oRow);
    expect(screen.getByText('GPT-4o — usage details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText(/42%/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Copilot Metrics API integration/)).toBeInTheDocument();
  });

  it('opens Claude model detail modal', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const claudeRow = screen.getByText('Claude 3.7').closest('[role="button"]')!;
    await user.click(claudeRow);
    expect(screen.getByText('Claude 3.7 — usage details')).toBeInTheDocument();
  });

  it('closes model modal via close button', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const gpt4oRow = screen.getByText('GPT-4o').closest('[role="button"]')!;
    await user.click(gpt4oRow);
    expect(screen.getByText('GPT-4o — usage details')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('GPT-4o — usage details')).not.toBeInTheDocument();
  });

  it('makes feature usage bar rows clickable', () => {
    render(<ModelsPane />);
    const ideRow = screen.getByText('IDE completions').closest('[role="button"]');
    expect(ideRow).toBeTruthy();
  });

  it('opens feature usage modal when clicking a feature row', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const ideRow = screen.getByText('IDE completions').closest('[role="button"]')!;
    await user.click(ideRow);
    expect(screen.getByText('IDE completions — usage details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText('142')).toBeInTheDocument();
  });

  it('makes editor cards clickable', () => {
    render(<ModelsPane />);
    const vsCodeWrapper = screen.getByText('VS Code').closest('[role="button"]');
    expect(vsCodeWrapper).toBeTruthy();
    expect(vsCodeWrapper).toHaveAttribute('tabIndex', '0');
  });

  it('opens editor detail modal when clicking an editor card', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const vsCodeWrapper = screen.getByText('VS Code').closest('[role="button"]')!;
    await user.click(vsCodeWrapper);
    expect(screen.getByText('VS Code — editor details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText('112')).toBeInTheDocument();
    expect(within(dialog).getByText(/User distribution by editor/)).toBeInTheDocument();
  });

  it('opens JetBrains editor modal', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const jbWrapper = screen.getByText('JetBrains').closest('[role="button"]')!;
    await user.click(jbWrapper);
    expect(screen.getByText('JetBrains — editor details')).toBeInTheDocument();
  });

  it('closes editor modal via close button', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const vsCodeWrapper = screen.getByText('VS Code').closest('[role="button"]')!;
    await user.click(vsCodeWrapper);
    expect(screen.getByText('VS Code — editor details')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('VS Code — editor details')).not.toBeInTheDocument();
  });

  it('shows sample data note in all modals', async () => {
    const user = userEvent.setup();
    render(<ModelsPane />);
    const gpt4oRow = screen.getByText('GPT-4o').closest('[role="button"]')!;
    await user.click(gpt4oRow);
    expect(
      screen.getByText(/Connect the Copilot Metrics API for live per-user data/),
    ).toBeInTheDocument();
  });
});
