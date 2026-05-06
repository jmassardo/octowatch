import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders title', () => {
    render(<PageHeader title="Dashboard" />);
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(<PageHeader title="Test" description="Some description" />);
    expect(screen.getByText('Some description')).toBeInTheDocument();
  });

  it('does not render description when not provided', () => {
    const { container } = render(<PageHeader title="Test" />);
    expect(container.querySelector('p')).toBeNull();
  });

  it('renders action buttons', async () => {
    const action = vi.fn();
    render(
      <PageHeader
        title="Test"
        actions={[{ label: 'Create', onClick: action, variant: 'primary' }]}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('renders breadcrumbs', () => {
    render(
      <PageHeader
        title="Test"
        breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Current' }]}
      />,
    );
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Current')).toBeInTheDocument();
  });

  it('renders breadcrumb links as anchors', () => {
    render(<PageHeader title="T" breadcrumbs={[{ label: 'Home', href: '/' }]} />);
    const link = screen.getByText('Home');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/');
  });

  it('renders disabled action button', () => {
    render(
      <PageHeader title="T" actions={[{ label: 'Save', onClick: vi.fn(), disabled: true }]} />,
    );
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
});
