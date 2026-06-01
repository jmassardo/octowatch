import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuditTrailPage } from './index';

describe('AuditTrailPage', () => {
  it('renders the page header', () => {
    render(
      <MemoryRouter>
        <AuditTrailPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('Audit Trail')).toBeInTheDocument();
  });

  it('renders the coming soon message', () => {
    render(
      <MemoryRouter>
        <AuditTrailPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('Audit Trail is coming soon.')).toBeInTheDocument();
  });
});
