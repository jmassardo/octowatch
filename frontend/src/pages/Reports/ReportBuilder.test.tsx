import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ReportBuilder } from './ReportBuilder';

vi.mock('../../hooks/useOrg');

vi.mock('../../api/reports', () => ({
  createCustomReport: vi.fn().mockResolvedValue({
    id: 1,
    name: 'Test Report',
    description: null,
    owner_login: 'testuser',
    data_sources: ['events'],
    columns: [],
    filters: [],
    grouping: { group_by: null, time_bucket: null },
    visualization: 'table',
    is_shared: false,
    shared_with: [],
    last_run_at: null,
    created_at: '2024-06-15T10:00:00Z',
    updated_at: '2024-06-15T10:00:00Z',
  }),
}));

describe('ReportBuilder', () => {
  const mockOnClose = vi.fn();
  const mockOnCreated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the report builder with step 1', () => {
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);
    expect(screen.getByTestId('report-builder')).toBeInTheDocument();
    expect(screen.getByText('Step 1: Choose Data Sources')).toBeInTheDocument();
  });

  it('renders all 6 data source options', () => {
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);
    expect(screen.getByText('Events')).toBeInTheDocument();
    expect(screen.getByText('Detections')).toBeInTheDocument();
    expect(screen.getByText('Security Posture')).toBeInTheDocument();
    expect(screen.getByText('Copilot')).toBeInTheDocument();
    expect(screen.getByText('Workflows')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
  });

  it('renders step indicators for all 6 steps', () => {
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);
    // 6 step dots
    const stepDots = screen.getByTestId('report-builder').querySelectorAll('[class*="stepDot"]');
    expect(stepDots.length).toBe(6);
  });

  it('can select a data source and proceed to step 2', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    const eventsSource = screen.getByText('Events');
    await user.click(eventsSource);

    const nextButton = screen.getByRole('button', { name: /Next/ });
    await user.click(nextButton);

    expect(screen.getByText('Step 2: Select Columns')).toBeInTheDocument();
  });

  it('step 2 shows columns from selected data source', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    expect(screen.getByText('Action')).toBeInTheDocument();
    expect(screen.getByText('Actor')).toBeInTheDocument();
    expect(screen.getByText('Organization')).toBeInTheDocument();
  });

  it('can navigate to step 3 filters', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    expect(screen.getByText('Step 3: Add Filters')).toBeInTheDocument();
  });

  it('can navigate to step 4 grouping', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    // Navigate through steps
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    expect(screen.getByText('Step 4: Choose Grouping')).toBeInTheDocument();
  });

  it('can navigate to step 5 visualization', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    expect(screen.getByText('Step 5: Choose Visualization')).toBeInTheDocument();
    expect(screen.getByText('Table only')).toBeInTheDocument();
    expect(screen.getByText('Table + Chart')).toBeInTheDocument();
    expect(screen.getByText('Chart only')).toBeInTheDocument();
  });

  it('can navigate to step 6 name and save', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    expect(screen.getByText('Step 6: Name and Save')).toBeInTheDocument();
    expect(screen.getByLabelText('Report name')).toBeInTheDocument();
    expect(screen.getByLabelText('Report description')).toBeInTheDocument();
  });

  it('previous button navigates back', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    expect(screen.getByText('Step 2: Select Columns')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Previous/ }));
    expect(screen.getByText('Step 1: Choose Data Sources')).toBeInTheDocument();
  });

  it('close button calls onClose', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByRole('button', { name: '✕' }));
    expect(mockOnClose).toHaveBeenCalledOnce();
  });

  it('save button calls createCustomReport and onCreated', async () => {
    const { createCustomReport } = await import('../../api/reports');
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    // Step 1: select source
    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    // Step 2-5: skip through
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    // Step 6: enter name and save
    const nameInput = screen.getByLabelText('Report name');
    await user.type(nameInput, 'My Test Report');

    await user.click(screen.getByRole('button', { name: 'Save Report' }));

    await waitFor(() => {
      expect(createCustomReport).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'My Test Report',
          data_sources: ['events'],
          visualization: 'table',
        }),
      );
    });

    await waitFor(() => {
      expect(mockOnCreated).toHaveBeenCalledOnce();
    });
  });

  it('save button is disabled without a name', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    const saveButton = screen.getByRole('button', { name: 'Save Report' });
    expect(saveButton).toBeDisabled();
  });

  it('step 6 shows summary of selections', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportBuilder onClose={mockOnClose} onCreated={mockOnCreated} />);

    await user.click(screen.getByText('Events'));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));
    await user.click(screen.getByRole('button', { name: /Next/ }));

    expect(screen.getByText('Summary')).toBeInTheDocument();
    expect(screen.getByText(/events/)).toBeInTheDocument();
  });
});
