import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CopilotTabBar } from './CopilotTabBar';

describe('CopilotTabBar', () => {
  const defaultProps = {
    activeTab: 'overview' as const,
    onTabChange: vi.fn(),
    anomalyCount: 3,
    blockerCount: 0,
  };

  it('renders all 10 tabs', () => {
    render(<CopilotTabBar {...defaultProps} />);
    const tablist = screen.getByRole('tablist');
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs).toHaveLength(10);
    expect(tabs[0]).toHaveTextContent('Overview');
    expect(tabs[1]).toHaveTextContent('Adoption');
    expect(tabs[2]).toHaveTextContent('Models & Features');
    expect(tabs[3]).toHaveTextContent('Teams');
    expect(tabs[4]).toHaveTextContent('Blockers');
    expect(tabs[5]).toHaveTextContent('License Optimization');
    expect(tabs[6]).toHaveTextContent('ROI');
    expect(tabs[7]).toHaveTextContent(/Anomalies/);
    expect(tabs[8]).toHaveTextContent('Policy Timeline');
    expect(tabs[9]).toHaveTextContent('Governance');
  });

  it('marks the active tab with aria-selected', () => {
    render(<CopilotTabBar {...defaultProps} activeTab="adoption" />);
    const adoptionTab = screen.getByRole('tab', { name: /Adoption/ });
    expect(adoptionTab).toHaveAttribute('aria-selected', 'true');

    const overviewTab = screen.getByRole('tab', { name: /Overview/ });
    expect(overviewTab).toHaveAttribute('aria-selected', 'false');
  });

  it('applies active class to active tab', () => {
    render(<CopilotTabBar {...defaultProps} activeTab="overview" />);
    const overviewTab = screen.getByRole('tab', { name: /Overview/ });
    expect(overviewTab.className).toContain('copilotTabActive');
  });

  it('shows badge on anomalies tab when count > 0', () => {
    render(<CopilotTabBar {...defaultProps} anomalyCount={3} />);
    const anomaliesTab = screen.getByRole('tab', { name: /Anomalies/ });
    expect(anomaliesTab).toHaveTextContent('3');
  });

  it('does not show badge when anomalyCount is 0', () => {
    render(<CopilotTabBar {...defaultProps} anomalyCount={0} />);
    const anomaliesTab = screen.getByRole('tab', { name: /Anomalies/ });
    expect(anomaliesTab.textContent).toBe('Anomalies');
  });

  it('does not show badge when anomalyCount is undefined', () => {
    render(<CopilotTabBar activeTab="overview" onTabChange={vi.fn()} />);
    const anomaliesTab = screen.getByRole('tab', { name: /Anomalies/ });
    expect(anomaliesTab.textContent).toBe('Anomalies');
  });

  it('shows badge on blockers tab when count > 0', () => {
    render(<CopilotTabBar {...defaultProps} blockerCount={5} />);
    const blockersTab = screen.getByRole('tab', { name: /Blockers/ });
    expect(blockersTab).toHaveTextContent('5');
  });

  it('does not show blockers badge when blockerCount is 0', () => {
    render(<CopilotTabBar {...defaultProps} blockerCount={0} />);
    const blockersTab = screen.getByRole('tab', { name: /Blockers/ });
    expect(blockersTab.textContent).toBe('Blockers');
  });

  it('calls onTabChange with correct tab id when clicked', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    render(<CopilotTabBar {...defaultProps} onTabChange={onTabChange} />);

    await user.click(screen.getByRole('tab', { name: /Models/ }));
    expect(onTabChange).toHaveBeenCalledWith('models');

    await user.click(screen.getByRole('tab', { name: /License/ }));
    expect(onTabChange).toHaveBeenCalledWith('license');

    await user.click(screen.getByRole('tab', { name: /Teams/ }));
    expect(onTabChange).toHaveBeenCalledWith('teams');

    await user.click(screen.getByRole('tab', { name: /ROI/ }));
    expect(onTabChange).toHaveBeenCalledWith('roi');
  });
});
