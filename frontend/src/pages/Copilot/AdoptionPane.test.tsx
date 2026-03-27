import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AdoptionPane } from './AdoptionPane';

function getDialog(): HTMLElement {
  return document.querySelector('.dialog')! as HTMLElement;
}

describe('AdoptionPane clickable stats', () => {
  it('makes tier cards clickable with role=button and tabIndex', () => {
    render(<AdoptionPane />);
    const powerCard = screen.getByText('Power Users').closest('[role="button"]');
    expect(powerCard).toBeTruthy();
    expect(powerCard).toHaveAttribute('tabIndex', '0');
  });

  it('opens Power Users tier modal with POWER_USERS table', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const powerCard = screen.getByText('Power Users').closest('[role="button"]')!;
    await user.click(powerCard);
    expect(screen.getByText('Power Users — 34 users')).toBeInTheDocument();
    // Modal should show user table - check inside modal
    const dialog = getDialog();
    expect(within(dialog).getByText('sarah.chen')).toBeInTheDocument();
  });

  it('opens Minimal tier modal with MINIMAL_USERS table', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const minimalCard = screen.getByText('Minimal').closest('[role="button"]')!;
    await user.click(minimalCard);
    expect(screen.getByText('Minimal — 22 users')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText('tom.jones')).toBeInTheDocument();
  });

  it('opens Regular tier modal with description and integration note', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const regularCard = screen.getByText('Regular').closest('[role="button"]')!;
    await user.click(regularCard);
    expect(screen.getByText('Regular — 68 users')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText(/Copilot Metrics API integration/)).toBeInTheDocument();
  });

  it('opens tier modal from stacked bar segment', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const segments = document.querySelectorAll('.stackedSegmentClickable');
    expect(segments.length).toBe(5);
    await user.click(segments[0] as HTMLElement);
    expect(screen.getByText('Power Users — 34 users')).toBeInTheDocument();
  });

  it('closes tier modal', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const powerCard = screen.getByText('Power Users').closest('[role="button"]')!;
    await user.click(powerCard);
    expect(screen.getByText('Power Users — 34 users')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Power Users — 34 users')).not.toBeInTheDocument();
  });

  it('shows toast when clicking streak in power users table', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const streakBtn = screen.getByText('45d').closest('[role="button"]')!;
    await user.click(streakBtn);
    expect(screen.getByText("View @sarah.chen's Copilot activity")).toBeInTheDocument();
  });

  it('shows toast when clicking accept rate in power users table', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const rateBtn = screen.getByText('42%').closest('[role="button"]')!;
    await user.click(rateBtn);
    expect(screen.getByText("View @sarah.chen's Copilot activity")).toBeInTheDocument();
  });

  it('makes feature adoption bars clickable', () => {
    render(<AdoptionPane />);
    const ideRow = screen.getByText('IDE completions').closest('[role="button"]');
    expect(ideRow).toBeTruthy();
    expect(ideRow).toHaveAttribute('tabIndex', '0');
  });

  it('opens feature adoption modal when clicking a feature bar', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const ideRow = screen.getByText('IDE completions').closest('[role="button"]')!;
    await user.click(ideRow);
    expect(screen.getByText('IDE completions — adoption details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText(/87%/)).toBeInTheDocument();
  });

  it('makes cycle time comparison clickable and opens modal', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    const ccrSection = screen.getByText('2.8h').closest('[role="button"]')!;
    await user.click(ccrSection);
    expect(screen.getByText('Cycle time comparison methodology')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText(/41% improvement/)).toBeInTheDocument();
  });

  it('makes minimal users Uses and Accepted cells clickable', () => {
    render(<AdoptionPane />);
    // Verify there are clickable stat buttons in the minimal users table area
    const clickableStats = screen.getAllByRole('button').filter(
      (el) => el.classList.contains('clickableStat'),
    );
    // Should have power users stats + minimal users stats
    expect(clickableStats.length).toBeGreaterThanOrEqual(6);
  });

  it('opens minimal user modal with activity summary', async () => {
    const user = userEvent.setup();
    render(<AdoptionPane />);
    // Find clickable stats that are within minimal users table
    const clickableStats = screen.getAllByRole('button').filter(
      (el) => el.classList.contains('clickableStat'),
    );
    // The last few clickable stats should be in the minimal users table
    // Find one that represents a "uses" or "accepted" count
    const minimalBtn = clickableStats.find((el) => el.textContent === '2');
    expect(minimalBtn).toBeTruthy();
    await user.click(minimalBtn!);
    const dialog = getDialog();
    expect(within(dialog).getByText(/Copilot Metrics API for live per-user data/)).toBeInTheDocument();
  });
});
