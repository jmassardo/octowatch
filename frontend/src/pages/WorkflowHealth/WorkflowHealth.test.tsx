import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { WorkflowHealthPage } from './index';

vi.mock('../../api/workflowMetrics', () => ({
  getAlwaysFailingWorkflows: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getAlwaysTimingOutWorkflows: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getWorkflowRunHistory: vi.fn().mockResolvedValue({ runs: [], workflow_path: '' }),
}));

describe('WorkflowHealthPage', () => {
  it('renders the page title', async () => {
    renderWithProviders(<WorkflowHealthPage />);
    expect(await screen.findByText('Workflow Health')).toBeInTheDocument();
  });

  it('renders the page description', async () => {
    renderWithProviders(<WorkflowHealthPage />);
    expect(
      await screen.findByText(
        'Operational health of CI/CD workflows — persistent failures and timeouts',
      ),
    ).toBeInTheDocument();
  });

  it('renders cross-link to Workflow Security page', async () => {
    renderWithProviders(<WorkflowHealthPage />);
    const link = await screen.findByRole('link', { name: /Workflow Security →/i });
    expect(link).toHaveAttribute('href', '/workflows');
  });

  it('renders the guidance box', async () => {
    renderWithProviders(<WorkflowHealthPage />);
    expect(await screen.findByText('What this page shows')).toBeInTheDocument();
  });

  it('renders guidance about operational failures vs security', async () => {
    renderWithProviders(<WorkflowHealthPage />);
    expect(await screen.findByText(/operational failures/i)).toBeInTheDocument();
  });

  it('renders the WorkflowMetricsTab content', async () => {
    renderWithProviders(<WorkflowHealthPage />);
    expect(await screen.findByText('Lookback period')).toBeInTheDocument();
    expect(
      await screen.findByText('No persistently failing workflows in this period'),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('No persistently timing-out workflows in this period'),
    ).toBeInTheDocument();
  });
});
