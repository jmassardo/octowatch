import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { RedirectAfterLogin } from './RedirectAfterLogin';

function renderWithRouter(initialPath: string = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<RedirectAfterLogin />} />
        <Route path="/dashboard" element={<p>Dashboard</p>} />
        <Route path="/events" element={<p>Events page</p>} />
        <Route path="/threats" element={<p>Threats page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RedirectAfterLogin', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('redirects to /dashboard when no saved URL exists', () => {
    renderWithRouter('/');
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('redirects to saved URL from localStorage', () => {
    localStorage.setItem('octowatch-return-url', '/events');
    renderWithRouter('/');
    expect(screen.getByText('Events page')).toBeInTheDocument();
  });

  it('clears the saved URL from localStorage after redirect', () => {
    localStorage.setItem('octowatch-return-url', '/threats');
    renderWithRouter('/');
    expect(screen.getByText('Threats page')).toBeInTheDocument();
    expect(localStorage.getItem('octowatch-return-url')).toBeNull();
  });

  it('falls back to /dashboard if saved URL is cleared externally', () => {
    // No saved URL
    renderWithRouter('/');
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });
});
