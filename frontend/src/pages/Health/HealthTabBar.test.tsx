import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HealthTabBar } from './HealthTabBar';

describe('HealthTabBar', () => {
  const defaultProps = {
    activeTab: 'repo-health' as const,
    onTabChange: vi.fn(),
  };

  it('renders all 8 tabs', () => {
    render(
      <MemoryRouter>
        <HealthTabBar {...defaultProps} />
      </MemoryRouter>,
    );
    const tablist = screen.getByRole('tablist');
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs).toHaveLength(8);
    expect(tabs[0]).toHaveTextContent('Repository Health');
    expect(tabs[1]).toHaveTextContent('Access & Identity');
    expect(tabs[2]).toHaveTextContent('Security Posture');
    expect(tabs[3]).toHaveTextContent('App Governance');
    expect(tabs[4]).toHaveTextContent('Operations');
    expect(tabs[5]).toHaveTextContent('License Health');
    expect(tabs[6]).toHaveTextContent('Maintenance Signals');
    expect(tabs[7]).toHaveTextContent('WAF Insights');
  });

  it('marks the active tab with aria-selected', () => {
    render(
      <MemoryRouter>
        <HealthTabBar {...defaultProps} activeTab="access-identity" />
      </MemoryRouter>,
    );
    const accessTab = screen.getByRole('tab', { name: /Access & Identity/ });
    expect(accessTab).toHaveAttribute('aria-selected', 'true');

    const repoTab = screen.getByRole('tab', { name: /Repository Health/ });
    expect(repoTab).toHaveAttribute('aria-selected', 'false');
  });

  it('applies active class to active tab', () => {
    render(
      <MemoryRouter>
        <HealthTabBar {...defaultProps} activeTab="repo-health" />
      </MemoryRouter>,
    );
    const repoTab = screen.getByRole('tab', { name: /Repository Health/ });
    expect(repoTab.className).toContain('healthTabActive');
  });

  it('does not apply active class to inactive tabs', () => {
    render(
      <MemoryRouter>
        <HealthTabBar {...defaultProps} activeTab="repo-health" />
      </MemoryRouter>,
    );
    const licenseTab = screen.getByRole('tab', { name: /License Health/ });
    expect(licenseTab.className).not.toContain('healthTabActive');
  });

  it('calls onTabChange with correct tab id when clicked', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    render(
      <MemoryRouter>
        <HealthTabBar {...defaultProps} onTabChange={onTabChange} />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('tab', { name: /Access & Identity/ }));
    expect(onTabChange).toHaveBeenCalledWith('access-identity');

    await user.click(screen.getByRole('tab', { name: /WAF Insights/ }));
    expect(onTabChange).toHaveBeenCalledWith('waf');
  });

  it('calls onTabChange for each tab', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    render(
      <MemoryRouter>
        <HealthTabBar {...defaultProps} onTabChange={onTabChange} />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('tab', { name: /License Health/ }));
    expect(onTabChange).toHaveBeenCalledWith('license');

    await user.click(screen.getByRole('tab', { name: /Maintenance Signals/ }));
    expect(onTabChange).toHaveBeenCalledWith('maintenance');
  });
});
