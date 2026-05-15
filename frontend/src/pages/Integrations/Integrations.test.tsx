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
    let navigatedTo = '';

    render(
      <MemoryRouter
        initialEntries={['/integrations']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route
            path="/settings/integrations"
            element={<div data-testid="settings-integrations">Settings Integrations</div>}
          />
        </Routes>
      </MemoryRouter>,
    );

    // The redirect should land on /settings/integrations
    navigatedTo = '/settings/integrations';
    expect(screen.getByTestId('settings-integrations')).toBeInTheDocument();
    expect(navigatedTo).toBe('/settings/integrations');
  });

  it('exports IntegrationsPage component', () => {
    expect(IntegrationsPage).toBeDefined();
    expect(typeof IntegrationsPage).toBe('function');
  });
});
