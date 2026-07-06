import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { IntegrationsPage } from './index';

/**
 * The IntegrationsPage now redirects to /settings/integrations.
 * These tests verify the redirect behavior.
 */
describe('IntegrationsPage', () => {
  it('redirects to /settings/integrations', () => {
    render(
      <MemoryRouter initialEntries={['/integrations']}>
        <Routes>
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route
            path="/settings/integrations"
            element={<div data-testid="settings-integrations">Settings Integrations</div>}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('settings-integrations')).toBeInTheDocument();
  });

  it('exports IntegrationsPage component', () => {
    expect(IntegrationsPage).toBeDefined();
    expect(typeof IntegrationsPage).toBe('function');
  });
});
