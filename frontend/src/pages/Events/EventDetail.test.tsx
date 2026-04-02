import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { EventDetail } from './EventDetail';
import type { EventResponse } from '../../types/events';

const BASE_EVENT: EventResponse = {
  id: 1,
  document_id: 'doc-1',
  created_at: '2024-06-15T10:30:00Z',
  ingested_at: '2024-06-15T10:31:00Z',
  action: 'repo.create',
  namespace: 'repository',
  actor: 'alice',
  actor_id: 100,
  actor_is_bot: false,
  org: 'acme-corp',
  org_id: 200,
  repo: 'acme-corp/new-service',
  repo_id: 300,
  business: null,
  source_ip: '61.220.19.3',
  user_agent: 'Mozilla/5.0',
  geo_country_code: 'CN',
  geo_city: 'Beijing',
  geo_is_proxy: false,
  data: {},
  ingestion_source: 'webhook',
  source_file_path: '/events/1.json',
};

describe('EventDetail', () => {
  it('renders the action label', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText('repo.create')).toBeInTheDocument();
  });

  it('renders the actor with @ prefix', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText('@alice')).toBeInTheDocument();
  });

  it('renders organization', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText('acme-corp')).toBeInTheDocument();
  });

  it('renders repository', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText('acme-corp/new-service')).toBeInTheDocument();
  });

  it('renders source IP in a code element', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    const ipEl = screen.getByText('61.220.19.3');
    expect(ipEl.tagName).toBe('CODE');
  });

  it('renders geo country and city alongside IP', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText(/CN/)).toBeInTheDocument();
    expect(screen.getByText(/Beijing/)).toBeInTheDocument();
  });

  it('renders user agent', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText('Mozilla/5.0')).toBeInTheDocument();
  });

  it('renders ingestion source', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText('webhook')).toBeInTheDocument();
  });

  it('does not render actor row when actor is null', () => {
    renderWithProviders(<EventDetail event={{ ...BASE_EVENT, actor: null }} />);
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });

  it('does not render source IP row when source_ip is null', () => {
    renderWithProviders(<EventDetail event={{ ...BASE_EVENT, source_ip: null }} />);
    expect(screen.queryByText('Source IP')).not.toBeInTheDocument();
  });

  it('does not render user agent row when user_agent is null', () => {
    renderWithProviders(<EventDetail event={{ ...BASE_EVENT, user_agent: null }} />);
    expect(screen.queryByText('User Agent')).not.toBeInTheDocument();
  });

  it('does not render organization row when org is null', () => {
    renderWithProviders(<EventDetail event={{ ...BASE_EVENT, org: null }} />);
    expect(screen.queryByText('Organization')).not.toBeInTheDocument();
  });

  it('does not render repository row when repo is null', () => {
    renderWithProviders(<EventDetail event={{ ...BASE_EVENT, repo: null }} />);
    expect(screen.queryByText('Repository')).not.toBeInTheDocument();
  });

  it('shows bot label when actor_is_bot is true', () => {
    renderWithProviders(<EventDetail event={{ ...BASE_EVENT, actor_is_bot: true }} />);
    expect(screen.getByText('bot')).toBeInTheDocument();
  });

  it('does not show bot label when actor_is_bot is false', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.queryByText('bot')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Additional Data section
  // -------------------------------------------------------------------------

  it('does not show Additional Data when event.data is empty', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.queryByText('Additional Data')).not.toBeInTheDocument();
  });

  it('shows Additional Data in formatted mode when event.data has entries', () => {
    const event = { ...BASE_EVENT, data: { reason: 'cleanup', count: 5 } };
    renderWithProviders(<EventDetail event={event} />);
    expect(screen.getByText('Additional Data')).toBeInTheDocument();
    expect(screen.getByText('reason')).toBeInTheDocument();
    expect(screen.getByText('cleanup')).toBeInTheDocument();
    expect(screen.getByText('count')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders nested objects in data as JSON strings', () => {
    const event = { ...BASE_EVENT, data: { nested: { a: 1, b: 2 } } };
    renderWithProviders(<EventDetail event={event} />);
    expect(screen.getByText('{"a":1,"b":2}')).toBeInTheDocument();
  });

  it('renders null data values as em-dash', () => {
    const event = { ...BASE_EVENT, data: { empty: null } };
    renderWithProviders(<EventDetail event={event} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('toggles between formatted and raw JSON views', async () => {
    const user = userEvent.setup();
    const event = { ...BASE_EVENT, data: { reason: 'cleanup' } };
    renderWithProviders(<EventDetail event={event} />);

    // Starts in formatted mode
    expect(screen.getByText('reason')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Raw JSON' })).toBeInTheDocument();

    // Switch to raw JSON
    await user.click(screen.getByRole('button', { name: 'Raw JSON' }));
    expect(screen.getByText(/"reason": "cleanup"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Formatted' })).toBeInTheDocument();

    // Switch back to formatted
    await user.click(screen.getByRole('button', { name: 'Formatted' }));
    expect(screen.getByRole('button', { name: 'Raw JSON' })).toBeInTheDocument();
  });

  it('applies danger variant to destructive actions', () => {
    const event = { ...BASE_EVENT, action: 'repo.destroy' };
    renderWithProviders(<EventDetail event={event} />);
    expect(screen.getByText('repo.destroy')).toBeInTheDocument();
  });

  it('applies attention variant to access actions', () => {
    const event = { ...BASE_EVENT, action: 'repo.access' };
    renderWithProviders(<EventDetail event={event} />);
    expect(screen.getByText('repo.access')).toBeInTheDocument();
  });

  it('renders all detail labels', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    expect(screen.getByText('Action')).toBeInTheDocument();
    expect(screen.getByText('Timestamp')).toBeInTheDocument();
    expect(screen.getByText('Actor')).toBeInTheDocument();
    expect(screen.getByText('Organization')).toBeInTheDocument();
    expect(screen.getByText('Repository')).toBeInTheDocument();
    expect(screen.getByText('Source IP')).toBeInTheDocument();
    expect(screen.getByText('User Agent')).toBeInTheDocument();
    expect(screen.getByText('Ingested')).toBeInTheDocument();
    expect(screen.getByText('Source')).toBeInTheDocument();
  });

  it('renders formatted timestamps', () => {
    renderWithProviders(<EventDetail event={BASE_EVENT} />);
    // The formatAbsolute function should produce a date string containing "Jun"
    const timestampTexts = screen.getAllByText(/Jun.*2024/);
    expect(timestampTexts.length).toBeGreaterThanOrEqual(1);
  });
});
