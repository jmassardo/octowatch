import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StatPill } from './StatPill';
import { StatPillConfigDrawer } from './StatPillConfig';
import { getDefaultStatPillConfig } from './statPillConfigStorage';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

describe('StatPill', () => {
  it('formats counts', () => {
    render(<StatPill id="events" icon="⚡" label="Events" value={1500} format="count" />);
    expect(screen.getByText('1.5K')).toBeInTheDocument();
  });

  it('formats percentages', () => {
    render(<StatPill id="coverage" icon="🛡️" label="Coverage" value={82.4} format="percentage" />);
    expect(screen.getByText('82.4%')).toBeInTheDocument();
  });

  it('formats durations', () => {
    render(<StatPill id="lag" icon="⏱️" label="Webhook Lag" value={150} format="duration" />);
    expect(screen.getByText('2.5h')).toBeInTheDocument();
  });

  it('renders trend indicators', () => {
    render(<StatPill id="adoption" icon="🤖" label="Adoption" value={72} format="percentage" trend={4.5} />);
    expect(screen.getByText('↑ 4.5%')).toBeInTheDocument();
  });

  it('applies warning styling', () => {
    render(<StatPill id="detections" icon="🚨" label="Critical" value={2} format="count" variant="warning" />);
    expect(screen.getByTestId('stat-pill-detections')).toHaveClass('warning');
  });

  it('navigates on click when a path is provided', async () => {
    const user = userEvent.setup();
    render(<StatPill id="clickable" icon="🔗" label="Open Detections" value={3} format="count" path="/threats" />);
    await user.click(screen.getByRole('button', { name: /Open Detections: 3/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/threats');
  });
});

describe('StatPillConfigDrawer', () => {
  it('opens and saves enabled pills plus thresholds', async () => {
    const user = userEvent.setup();
    const handleSave = vi.fn();

    render(
      <StatPillConfigDrawer
        open={true}
        onClose={() => {}}
        config={getDefaultStatPillConfig()}
        onSave={handleSave}
      />,
    );

    await user.click(screen.getAllByRole('checkbox')[0]!);
    const warningInput = screen.getByLabelText('Secret Alerts warning threshold');
    await user.clear(warningInput);
    await user.type(warningInput, '2');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(handleSave).toHaveBeenCalledWith(
      expect.objectContaining({
        enabledPills: expect.not.arrayContaining(['open-detections']),
        thresholds: expect.objectContaining({
          'secret-alerts': expect.objectContaining({ warning: 2 }),
        }),
      }),
    );
  });

  it('resets the drawer back to defaults', async () => {
    const user = userEvent.setup();
    const handleSave = vi.fn();
    const custom = getDefaultStatPillConfig();
    custom.enabledPills = ['secret-alerts'];

    render(
      <StatPillConfigDrawer open={true} onClose={() => {}} config={custom} onSave={handleSave} />,
    );

    await user.click(screen.getByRole('button', { name: /Reset to defaults/i }));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(handleSave).toHaveBeenCalledWith(
      expect.objectContaining({
        enabledPills: expect.arrayContaining(['open-detections', 'secret-alerts']),
      }),
    );
  });
});
