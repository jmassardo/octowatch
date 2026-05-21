import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { PaginatedOrgList } from './PaginatedOrgList';

function generateOrgs(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `org-${String(i + 1).padStart(4, '0')}`);
}

describe('PaginatedOrgList', () => {
  it('renders all organizations on one page when count is small', () => {
    const orgs = ['alpha', 'beta', 'gamma'];
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={orgs}
        onSelectionChange={onChange}
      />,
    );

    expect(screen.getByLabelText(/alpha/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/beta/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/gamma/i)).toBeInTheDocument();
    expect(screen.getByText(/3 orgs/)).toBeInTheDocument();
  });

  it('paginates when organizations exceed page size (20)', () => {
    const orgs = generateOrgs(45);
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={[]}
        onSelectionChange={onChange}
      />,
    );

    // First page shows first 20
    expect(screen.getByLabelText(/org-0001/)).toBeInTheDocument();
    expect(screen.getByLabelText(/org-0020/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/org-0021/)).not.toBeInTheDocument();

    // Pagination info visible
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
    expect(screen.getByText(/45 total/)).toBeInTheDocument();
  });

  it('navigates between pages', async () => {
    const user = userEvent.setup();
    const orgs = generateOrgs(45);
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={[]}
        onSelectionChange={onChange}
      />,
    );

    await user.click(screen.getByRole('button', { name: /next/i }));

    expect(screen.getByLabelText(/org-0021/)).toBeInTheDocument();
    expect(screen.getByLabelText(/org-0040/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/org-0001/)).not.toBeInTheDocument();
    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument();
  });

  it('filters organizations by search query', async () => {
    const user = userEvent.setup();
    const orgs = ['acme-corp', 'globex-inc', 'acme-labs', 'initech'];
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={orgs}
        onSelectionChange={onChange}
      />,
    );

    const searchInput = screen.getByPlaceholderText(/search organizations/i);
    await user.type(searchInput, 'acme');

    expect(screen.getByLabelText(/acme-corp/)).toBeInTheDocument();
    expect(screen.getByLabelText(/acme-labs/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/globex-inc/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/initech/)).not.toBeInTheDocument();
    expect(screen.getByText(/2 orgs/)).toBeInTheDocument();
  });

  it('resets to page 1 when search query changes', async () => {
    const user = userEvent.setup();
    const orgs = generateOrgs(45);
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={[]}
        onSelectionChange={onChange}
      />,
    );

    // Go to page 2
    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument();

    // Type a very specific search - should reset to page 1
    const searchInput = screen.getByPlaceholderText(/search organizations/i);
    await user.type(searchInput, 'org-0045');

    // Should filter to 1 result - pagination hides when only 1 page
    expect(screen.getByLabelText(/org-0045/)).toBeInTheDocument();
    expect(screen.getByText(/1 org/)).toBeInTheDocument();
    // Pagination controls should not be visible for a single result
    expect(screen.queryByText(/Page 2/)).not.toBeInTheDocument();
  });

  it('preserves selection state across pages', async () => {
    const user = userEvent.setup();
    const orgs = generateOrgs(25);
    const selected: string[] = ['org-0001'];
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={selected}
        onSelectionChange={onChange}
      />,
    );

    // org-0001 is checked on page 1
    expect(screen.getByLabelText(/org-0001/)).toBeChecked();

    // Navigate to page 2 and select an org
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByLabelText(/org-0021/));

    // Should receive both originally selected and newly selected
    expect(onChange).toHaveBeenCalledWith(expect.arrayContaining(['org-0001', 'org-0021']));
  });

  it('shows empty state when search matches nothing', async () => {
    const user = userEvent.setup();
    const orgs = ['alpha', 'beta', 'gamma'];
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={orgs}
        onSelectionChange={onChange}
      />,
    );

    const searchInput = screen.getByPlaceholderText(/search organizations/i);
    await user.type(searchInput, 'zzz');

    expect(screen.getByText(/no organizations matching "zzz"/i)).toBeInTheDocument();
  });

  it('select all on page selects only visible items', async () => {
    const user = userEvent.setup();
    const orgs = generateOrgs(25);
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={[]}
        onSelectionChange={onChange}
      />,
    );

    await user.click(screen.getByRole('button', { name: /select all on page/i }));

    const call = onChange.mock.calls[0][0] as string[];
    expect(call).toHaveLength(20);
    expect(call).toContain('org-0001');
    expect(call).toContain('org-0020');
    expect(call).not.toContain('org-0021');
  });

  it('deselect all on page removes only visible items', async () => {
    const user = userEvent.setup();
    const orgs = generateOrgs(25);
    // All 25 selected
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={[...orgs]}
        onSelectionChange={onChange}
      />,
    );

    await user.click(screen.getByRole('button', { name: /deselect all on page/i }));

    const call = onChange.mock.calls[0][0] as string[];
    // Only page 2 items remain (5 items)
    expect(call).toHaveLength(5);
    expect(call).toContain('org-0021');
    expect(call).not.toContain('org-0001');
  });

  it('displays selection count in result summary', () => {
    const orgs = ['alpha', 'beta', 'gamma', 'delta'];
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={['alpha', 'gamma']}
        onSelectionChange={onChange}
      />,
    );

    expect(screen.getByText(/4 orgs · 2 selected/)).toBeInTheDocument();
  });

  it('handles search case-insensitively', async () => {
    const user = userEvent.setup();
    const orgs = ['AcmeCorp', 'GlobexInc', 'INITECH'];
    const onChange = vi.fn();

    renderWithProviders(
      <PaginatedOrgList
        organizations={orgs}
        selectedOrganizations={[]}
        onSelectionChange={onChange}
      />,
    );

    const searchInput = screen.getByPlaceholderText(/search organizations/i);
    await user.type(searchInput, 'ACME');

    expect(screen.getByLabelText(/AcmeCorp/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/GlobexInc/)).not.toBeInTheDocument();
  });
});
