import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ExecutiveView } from './ExecutiveView';

// Mock the executive API
const mockGetExecutiveSummary = vi.fn().mockResolvedValue({
  posture_score: 82,
  posture_score_previous: 79,
  score_delta: 3,
  score_delta_pct: 3.8,
  detection_trend: { '7d': 5, '30d': 18, '90d': 42 },
  severity_breakdown: { critical: 2, high: 5, medium: 8, low: 3 },
  compliance_summary: [
    { framework: 'SOC 2', controls_assessed: 14, controls_with_evidence: 12, compliance_pct: 85.7 },
    { framework: 'ISO 27001', controls_assessed: 11, controls_with_evidence: 10, compliance_pct: 90.9 },
    { framework: 'NIST', controls_assessed: 11, controls_with_evidence: 8, compliance_pct: 72.7 },
  ],
  top_risks: [
    {
      title: 'Excessive admin access',
      severity: 'high',
      category: 'access',
      count: 5,
      actor: null,
    },
  ],
  month_over_month: {
    current_detections: 18,
    previous_detections: 15,
    current_events: 1200,
    previous_events: 1000,
    detection_change_pct: 20.0,
    event_change_pct: 20.0,
  },
});

const mockExportExecutivePdf = vi.fn().mockResolvedValue(new Blob(['<html></html>']));

vi.mock('../../api/executive', () => ({
  getExecutiveSummary: (...args: unknown[]) => mockGetExecutiveSummary(...args),
  exportExecutivePdf: (...args: unknown[]) => mockExportExecutivePdf(...args),
}));

vi.mock('../../components/charts/LineAreaChart', () => ({
  LineAreaChart: () => <div data-testid="line-area-chart" />,
}));

describe('ExecutiveView', () => {
  it('renders loading state then summary data', async () => {
    renderWithProviders(<ExecutiveView />);

    await waitFor(() => {
      expect(screen.getByText('82')).toBeInTheDocument();
    });
  });

  it('displays posture score and delta', async () => {
    renderWithProviders(<ExecutiveView />);

    await waitFor(() => {
      expect(screen.getByText('82')).toBeInTheDocument();
      // Delta shows as "3.0 (3.8%)" with ▲
      expect(screen.getByText(/3\.0/)).toBeInTheDocument();
    });
  });

  it('displays compliance summary cards', async () => {
    renderWithProviders(<ExecutiveView />);

    await waitFor(() => {
      expect(screen.getByText('SOC 2')).toBeInTheDocument();
      expect(screen.getByText('ISO 27001')).toBeInTheDocument();
      expect(screen.getByText('NIST')).toBeInTheDocument();
    });
  });

  it('displays top risks', async () => {
    renderWithProviders(<ExecutiveView />);

    await waitFor(() => {
      expect(screen.getByText('Excessive admin access')).toBeInTheDocument();
    });
  });

  it('displays month-over-month metrics', async () => {
    renderWithProviders(<ExecutiveView />);

    await waitFor(() => {
      expect(screen.getByText('Events')).toBeInTheDocument();
      expect(screen.getByText('Detections')).toBeInTheDocument();
    });
  });

  it('allows period toggle', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ExecutiveView />);

    await waitFor(() => {
      expect(screen.getByText('82')).toBeInTheDocument();
    });

    const btn7 = screen.getByRole('button', { name: '7d' });
    await user.click(btn7);
    expect(mockGetExecutiveSummary).toHaveBeenCalledWith(7);
  });

  it('shows export PDF button', async () => {
    renderWithProviders(<ExecutiveView />);

    await waitFor(() => {
      expect(screen.getByText('82')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /export as pdf/i })).toBeInTheDocument();
  });
});
