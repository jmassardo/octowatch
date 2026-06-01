import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PlatformUsagePage } from './index';

describe('PlatformUsagePage', () => {
  it('renders the page header', () => {
    render(
      <MemoryRouter>
        <PlatformUsagePage />
      </MemoryRouter>,
    );
    expect(screen.getByText('Platform Usage')).toBeInTheDocument();
  });

  it('renders the coming soon message', () => {
    render(
      <MemoryRouter>
        <PlatformUsagePage />
      </MemoryRouter>,
    );
    expect(screen.getByText('Platform Usage monitoring is coming soon.')).toBeInTheDocument();
  });
});
