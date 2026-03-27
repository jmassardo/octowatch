import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CopilotPage } from './index';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

vi.mock('../../api/reports', () => ({
  getSeatUtilizationReport: vi.fn().mockResolvedValue({ data: [] }),
  getCopilotSeatsReport: vi.fn().mockResolvedValue({ data: [] }),
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CopilotPage />
    </QueryClientProvider>,
  );
}

describe('CopilotPage', () => {
  it('renders page title and subtitle', () => {
    renderPage();
    expect(screen.getByText('Copilot Insights')).toBeInTheDocument();
    expect(
      screen.getByText(
        'GitHub Copilot adoption, seat utilization, and correlation with delivery outcomes',
      ),
    ).toBeInTheDocument();
  });

  it('renders the tab bar with 5 tabs', () => {
    renderPage();
    const tablist = screen.getByRole('tablist');
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs).toHaveLength(5);
  });

  it('shows the anomaly badge with count 3', () => {
    renderPage();
    const tablist = screen.getByRole('tablist');
    const anomaliesTab = within(tablist).getByRole('tab', { name: /Anomalies/ });
    expect(anomaliesTab).toHaveTextContent('3');
  });

  it('shows overview content by default', () => {
    renderPage();
    expect(screen.getByText(/Seat waste detected/)).toBeInTheDocument();
    expect(screen.getByText('Export inactive list')).toBeInTheDocument();
  });

  it('switches to the adoption tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Adoption/ }));
    expect(screen.getByText('Adoption tiers')).toBeInTheDocument();
    expect(screen.getByText('Power Users')).toBeInTheDocument();
    expect(screen.getByText('Daily power users')).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('switches to the models tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Models/ }));
    expect(screen.getByText('Model usage spread')).toBeInTheDocument();
    expect(screen.getByText('Feature usage spread')).toBeInTheDocument();
    expect(screen.getByText('Editor breakdown')).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('switches to the license tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /License/ }));
    expect(screen.getByText('Cost optimization summary')).toBeInTheDocument();
    expect(screen.getByText('Recommendations')).toBeInTheDocument();
    expect(screen.getByText(/Enable just-in-time provisioning/)).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('switches to the anomalies tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Anomalies/ }));
    expect(screen.getByText('Sudden drop in acceptance rate')).toBeInTheDocument();
    expect(screen.getByText('Unusual seat churn detected')).toBeInTheDocument();
    expect(screen.getByText('Knowledge base usage spike')).toBeInTheDocument();
    expect(screen.getByText(/3 anomalies detected/)).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('can switch back to overview after navigating to another tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Adoption/ }));
    expect(screen.getByText('Adoption tiers')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /Overview/ }));
    expect(screen.getByText(/Seat waste detected/)).toBeInTheDocument();
    expect(screen.queryByText('Adoption tiers')).not.toBeInTheDocument();
  });
});
