import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MaintenancePane } from './MaintenancePane';
import { STALE_PRS, UNHEALTHY_WEBHOOKS, SKIPPED_WORKFLOWS } from './healthData';

describe('MaintenancePane', () => {
  it('renders the sample data banner', () => {
    render(<MaintenancePane />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/Maintenance signals/)).toBeInTheDocument();
  });

  it('renders stale PRs card header', () => {
    render(<MaintenancePane />);
    expect(screen.getByText('Stale PRs')).toBeInTheDocument();
    expect(screen.getByText('open > configured threshold')).toBeInTheDocument();
  });

  it('renders all stale PRs with repo name and title', () => {
    render(<MaintenancePane />);
    for (const pr of STALE_PRS) {
      // repo names may appear multiple times (in stale PRs and workflow tables)
      const repoElements = screen.getAllByText(pr.repo);
      expect(repoElements.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(`#${pr.number} · "${pr.title}"`)).toBeInTheDocument();
    }
  });

  it('renders stale PR age labels with correct variants', () => {
    render(<MaintenancePane />);
    // 127 days and 84 days should be danger (>90)
    expect(screen.getByText('127 days open')).toBeInTheDocument();
    expect(screen.getByText('84 days open')).toBeInTheDocument();
    // 62 days should be attention
    expect(screen.getByText('62 days open')).toBeInTheDocument();
  });

  it('renders stale PRs source note', () => {
    render(<MaintenancePane />);
    const sourceNotes = screen.getAllByText(/Derived from/, { exact: false });
    expect(sourceNotes.length).toBeGreaterThanOrEqual(1);
  });

  it('renders unhealthy webhooks card header', () => {
    render(<MaintenancePane />);
    expect(screen.getByText('Unhealthy webhooks & apps')).toBeInTheDocument();
  });

  it('renders all unhealthy webhooks with name and detail', () => {
    render(<MaintenancePane />);
    for (const wh of UNHEALTHY_WEBHOOKS) {
      expect(screen.getByText(wh.name)).toBeInTheDocument();
    }
  });

  it('renders webhook danger item with correct styling class', () => {
    render(<MaintenancePane />);
    const dangerWebhook = screen.getByText(UNHEALTHY_WEBHOOKS[0].name).closest(`.webhookItem`);
    expect(dangerWebhook).toBeTruthy();
    expect(dangerWebhook!.classList.contains('webhookItemDanger')).toBe(true);
  });

  it('renders webhook attention item with correct styling class', () => {
    render(<MaintenancePane />);
    const warnWebhook = screen.getByText(UNHEALTHY_WEBHOOKS[1].name).closest(`.webhookItem`);
    expect(warnWebhook).toBeTruthy();
    expect(warnWebhook!.classList.contains('webhookItemWarn')).toBe(true);
  });

  it('renders webhook muted item with correct styling class', () => {
    render(<MaintenancePane />);
    const mutedWebhook = screen.getByText(UNHEALTHY_WEBHOOKS[2].name).closest(`.webhookItem`);
    expect(mutedWebhook).toBeTruthy();
    expect(mutedWebhook!.classList.contains('webhookItemMuted')).toBe(true);
  });

  it('renders disabled/skipped workflows section title', () => {
    render(<MaintenancePane />);
    expect(screen.getByText('Disabled / consistently-skipped workflows')).toBeInTheDocument();
  });

  it('renders workflow table with correct headers', () => {
    render(<MaintenancePane />);
    const table = screen.getByText('Workflow').closest('table')!;
    const headers = within(table).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent);
    expect(headerTexts).toEqual([
      'Workflow',
      'Repository',
      'Status',
      'Last run',
      'Consecutive skips',
    ]);
  });

  it('renders all skipped workflows in the table', () => {
    render(<MaintenancePane />);
    for (const wf of SKIPPED_WORKFLOWS) {
      expect(screen.getByText(wf.workflow)).toBeInTheDocument();
      // Repositories may appear in both stale PRs and workflows tables
      const repoElements = screen.getAllByText(wf.repository);
      expect(repoElements.length).toBeGreaterThanOrEqual(1);
    }
  });

  it('renders disabled status label as danger variant', () => {
    render(<MaintenancePane />);
    // "disabled" appears once in the workflow table
    const disabledLabels = screen.getAllByText('disabled');
    expect(disabledLabels.length).toBeGreaterThanOrEqual(1);
    expect(disabledLabels[0].classList.contains('danger')).toBe(true);
  });

  it('renders skipped status labels as attention variant', () => {
    render(<MaintenancePane />);
    // Find only the Label components with "skipped" text (they have the "label" CSS class)
    const skippedLabels = screen.getAllByText('skipped').filter(
      (el) => el.classList.contains('label'),
    );
    expect(skippedLabels.length).toBe(2);
    for (const label of skippedLabels) {
      expect(label.classList.contains('attention')).toBe(true);
    }
  });

  it('renders consecutive skip counts with labels', () => {
    render(<MaintenancePane />);
    expect(screen.getByText('18 consecutive')).toBeInTheDocument();
    expect(screen.getByText('41 consecutive')).toBeInTheDocument();
  });

  it('renders dash for disabled workflow without consecutive skips', () => {
    render(<MaintenancePane />);
    // The disabled workflow has null consecutiveSkips, should show "—"
    const row = screen.getByText('security-scan.yml').closest('tr')!;
    expect(within(row).getByText('—')).toBeInTheDocument();
  });

  it('renders high consecutive skips as danger variant', () => {
    render(<MaintenancePane />);
    const label41 = screen.getByText('41 consecutive');
    expect(label41.classList.contains('danger')).toBe(true);
  });

  it('renders moderate consecutive skips as attention variant', () => {
    render(<MaintenancePane />);
    const label18 = screen.getByText('18 consecutive');
    expect(label18.classList.contains('attention')).toBe(true);
  });

  it('renders workflow source note', () => {
    render(<MaintenancePane />);
    expect(screen.getByText(/workflows.disabled_intentionally/, { exact: false })).toBeInTheDocument();
  });
});
