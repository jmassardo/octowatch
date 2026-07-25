import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { LoginPage } from './LoginPage';

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders the login page', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('OctoWatch')).toBeInTheDocument();
    expect(screen.getByText('Sign in with GitHub')).toBeInTheDocument();
  });

  it('applies dark theme from localStorage on render', () => {
    localStorage.setItem('octowatch-theme', 'dark');
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('applies light theme from localStorage on render', () => {
    localStorage.setItem('octowatch-theme', 'light');
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('does not set data-theme when system theme is preferred', () => {
    // No localStorage entry means system theme
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });
});
