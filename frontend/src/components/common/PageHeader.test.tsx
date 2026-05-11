import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PageHeader } from './PageHeader';

vi.mock('../../hooks/useHelp', async () => {
  const React = await vi.importActual<typeof import('react')>('react');

  return {
    useHelp: () => {
      const [isHelpOpen, setIsHelpOpen] = React.useState(false);

      return {
        helpContent: {
          title: 'Test Help',
          description: 'Helpful context for this header.',
          concepts: [{ term: 'Concept', definition: 'Definition' }],
          tasks: [{ title: 'Task', steps: ['Step'] }],
          relatedPages: [{ title: 'Related', path: '/related' }],
        },
        openHelp: () => setIsHelpOpen(true),
        closeHelp: () => setIsHelpOpen(false),
        isHelpOpen,
      };
    },
  };
});

describe('PageHeader', () => {
  it('renders title', () => {
    render(<PageHeader title="Dashboard" />);
    expect(screen.getByRole('heading', { name: 'Dashboard', level: 1 })).toBeInTheDocument();
  });

  it('renders a custom heading level when provided', () => {
    render(<PageHeader title="Section" headingLevel={2} />);
    expect(screen.getByRole('heading', { name: 'Section', level: 2 })).toBeInTheDocument();
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
    expect(screen.getByRole('group', { name: /test actions/i })).toBeInTheDocument();
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

  it('renders help button and opens the help panel', async () => {
    render(<PageHeader title="Dashboard" showHelp />);

    await userEvent.click(screen.getByRole('button', { name: /open help panel/i }));

    expect(screen.getByRole('dialog', { name: 'Test Help' })).toBeInTheDocument();
    expect(screen.getByText('About this page')).toBeInTheDocument();
  });
});
