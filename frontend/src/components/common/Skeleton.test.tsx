import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { SkeletonCard } from './SkeletonCard';
import { SkeletonTable } from './SkeletonTable';
import { SkeletonChart } from './SkeletonChart';

describe('SkeletonCard', () => {
  it('renders with default 3 lines', () => {
    const { container } = render(<SkeletonCard />);
    expect(container.querySelectorAll('[class*="skeleton"]').length).toBe(3);
  });

  it('renders custom number of lines', () => {
    const { container } = render(<SkeletonCard lines={5} />);
    expect(container.querySelectorAll('[class*="skeleton"]').length).toBe(5);
  });

  it('has aria-hidden for a11y', () => {
    const { container } = render(<SkeletonCard />);
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true');
  });

  it('accepts className prop', () => {
    const { container } = render(<SkeletonCard className="custom" />);
    expect(container.firstElementChild?.className).toContain('custom');
  });
});

describe('SkeletonTable', () => {
  it('renders header + data rows', () => {
    const { container } = render(<SkeletonTable columns={3} rows={4} />);
    const rows = container.querySelectorAll('[class*="tableRow"]');
    // 1 header row + 4 data rows = 5
    expect(rows.length).toBe(5);
  });

  it('renders correct number of cells per row', () => {
    const { container } = render(<SkeletonTable columns={3} rows={2} />);
    const firstRow = container.querySelector('[class*="tableRow"]');
    expect(firstRow?.children.length).toBe(3);
  });
});

describe('SkeletonChart', () => {
  it('renders default 8 bars', () => {
    const { container } = render(<SkeletonChart />);
    expect(container.querySelectorAll('[class*="chartBar"]').length).toBe(8);
  });

  it('renders custom number of bars', () => {
    const { container } = render(<SkeletonChart bars={5} />);
    expect(container.querySelectorAll('[class*="chartBar"]').length).toBe(5);
  });
});
