import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { PlaybooksPage } from './index';

// Mock navigate
const mockNavigate = vi.fn();
vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock playbooks API
const mockListTemplates = vi.fn().mockResolvedValue([]);
const mockListExecutions = vi.fn().mockResolvedValue({ items: [], total: 0 });
const mockCreateTemplate = vi.fn().mockResolvedValue({});
const mockUpdateTemplate = vi.fn().mockResolvedValue({});
const mockDeleteTemplate = vi.fn().mockResolvedValue(undefined);

vi.mock('../../api/playbooks', () => ({
  listPlaybookTemplates: (...args: unknown[]) => mockListTemplates(...args),
  listPlaybookExecutions: (...args: unknown[]) => mockListExecutions(...args),
  createPlaybookTemplate: (...args: unknown[]) => mockCreateTemplate(...args),
  updatePlaybookTemplate: (...args: unknown[]) => mockUpdateTemplate(...args),
  deletePlaybookTemplate: (...args: unknown[]) => mockDeleteTemplate(...args),
  getPlaybookTemplate: vi.fn().mockResolvedValue(null),
  getPlaybookExecution: vi.fn().mockResolvedValue(null),
  executePlaybook: vi.fn().mockResolvedValue({}),
  completePlaybookStep: vi.fn().mockResolvedValue({}),
  skipPlaybookStep: vi.fn().mockResolvedValue({}),
  completePlaybookExecution: vi.fn().mockResolvedValue({}),
}));

const sampleTemplates = [
  {
    id: 1,
    name: 'Account Compromise Response',
    slug: 'account-compromise-response',
    description: 'Step-by-step response to account compromise.',
    detection_categories: ['account_compromise'],
    steps: [
      { title: 'Disable Account', description: 'Suspend the user', action_type: 'manual' },
      { title: 'Review Activity', description: 'Check logs', action_type: 'manual' },
    ],
    created_by: 'admin',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'Leaked Secret Response',
    slug: 'leaked-secret-response',
    description: 'Response for leaked secrets.',
    detection_categories: ['data_exfiltration'],
    steps: [{ title: 'Revoke Secret', description: 'Revoke it', action_type: 'manual' }],
    created_by: 'admin',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
];

const sampleExecutions = {
  items: [
    {
      id: 1,
      template_id: 1,
      detection_id: 10,
      status: 'in_progress',
      step_results: [
        { step_index: 0, title: 'Disable Account', completed: true, notes: '' },
        { step_index: 1, title: 'Review Activity', completed: false, notes: '' },
      ],
      started_by: 'testuser',
      started_at: '2025-01-01T00:00:00Z',
      completed_at: null,
    },
    {
      id: 2,
      template_id: 2,
      detection_id: 20,
      status: 'completed',
      step_results: [{ step_index: 0, title: 'Revoke Secret', completed: true, notes: 'Done' }],
      started_by: 'admin',
      started_at: '2025-01-01T00:00:00Z',
      completed_at: '2025-01-02T00:00:00Z',
    },
  ],
  total: 2,
};

describe('PlaybooksPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockListTemplates.mockClear();
    mockListExecutions.mockClear();
    mockListTemplates.mockResolvedValue([]);
    mockListExecutions.mockResolvedValue({ items: [], total: 0 });
  });

  /* ─── Page header ─────────────────────────── */

  it('renders the page title', () => {
    renderWithProviders(<PlaybooksPage />);
    expect(screen.getByText('Playbooks')).toBeInTheDocument();
  });

  it('renders the page description', () => {
    renderWithProviders(<PlaybooksPage />);
    expect(
      screen.getByText('Guided remediation workflows for incident response'),
    ).toBeInTheDocument();
  });

  /* ─── Tabs ────────────────────────────────── */

  it('renders all three tabs', () => {
    renderWithProviders(<PlaybooksPage />);
    expect(screen.getByText('Template Library')).toBeInTheDocument();
    expect(screen.getByText(/Active/)).toBeInTheDocument();
    expect(screen.getByText(/History/)).toBeInTheDocument();
  });

  it('defaults to template library tab', () => {
    renderWithProviders(<PlaybooksPage />);
    const tab = screen.getByText('Template Library');
    expect(tab.getAttribute('aria-selected')).toBe('true');
  });

  /* ─── Template Library ────────────────────── */

  it('shows empty state when no templates exist', async () => {
    mockListTemplates.mockResolvedValue([]);
    renderWithProviders(<PlaybooksPage />);
    expect(await screen.findByText('No playbook templates')).toBeInTheDocument();
  });

  it('displays template cards when templates are loaded', async () => {
    mockListTemplates.mockResolvedValue(sampleTemplates);
    renderWithProviders(<PlaybooksPage />);
    expect(await screen.findByText('Account Compromise Response')).toBeInTheDocument();
    expect(screen.getByText('Leaked Secret Response')).toBeInTheDocument();
  });

  it('shows step count in the template table', async () => {
    mockListTemplates.mockResolvedValue(sampleTemplates);
    renderWithProviders(<PlaybooksPage />);

    const firstTemplate = await screen.findByText('Account Compromise Response');
    const firstRow = firstTemplate.closest('tr');
    expect(firstRow).not.toBeNull();
    expect(within(firstRow!).getByText('2')).toBeInTheDocument();

    const secondTemplate = screen.getByText('Leaked Secret Response');
    const secondRow = secondTemplate.closest('tr');
    expect(secondRow).not.toBeNull();
    expect(within(secondRow!).getByText('1')).toBeInTheDocument();
  });

  it('shows template description', async () => {
    mockListTemplates.mockResolvedValue(sampleTemplates);
    renderWithProviders(<PlaybooksPage />);
    expect(
      await screen.findByText('Step-by-step response to account compromise.'),
    ).toBeInTheDocument();
  });

  /* ─── Active Executions ───────────────────── */

  it('switches to active tab and shows empty state', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PlaybooksPage />);
    await user.click(screen.getByText(/Active/));
    expect(await screen.findByText('No active executions')).toBeInTheDocument();
  });

  it('shows active executions in data table', async () => {
    const user = userEvent.setup();
    mockListTemplates.mockResolvedValue(sampleTemplates);
    mockListExecutions.mockResolvedValue(sampleExecutions);
    renderWithProviders(<PlaybooksPage />);
    await user.click(screen.getByText(/Active/));
    expect(await screen.findByText('#10')).toBeInTheDocument();
    expect(screen.getByText('Continue')).toBeInTheDocument();
  });

  /* ─── History tab ─────────────────────────── */

  it('switches to history tab and shows completed executions', async () => {
    const user = userEvent.setup();
    mockListTemplates.mockResolvedValue(sampleTemplates);
    mockListExecutions.mockResolvedValue(sampleExecutions);
    renderWithProviders(<PlaybooksPage />);
    await user.click(screen.getByText(/History/));
    expect(await screen.findByText('#20')).toBeInTheDocument();
  });

  /* ─── New Template button ─────────────────── */

  it('shows the new template button', () => {
    renderWithProviders(<PlaybooksPage />);
    expect(screen.getByText('+ New Template')).toBeInTheDocument();
  });

  it('opens editor when new template is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PlaybooksPage />);
    await user.click(screen.getByText('+ New Template'));
    expect(screen.getByText('Create Playbook Template')).toBeInTheDocument();
  });

  /* ─── Edit template ──────────────────────── */

  it('opens editor when a template row is clicked', async () => {
    const user = userEvent.setup();
    mockListTemplates.mockResolvedValue(sampleTemplates);
    renderWithProviders(<PlaybooksPage />);

    const templateName = await screen.findByText('Account Compromise Response');
    const templateRow = templateName.closest('tr');
    expect(templateRow).not.toBeNull();

    await user.click(templateRow!);
    expect(screen.getByText('Edit Playbook Template')).toBeInTheDocument();
  });
});
