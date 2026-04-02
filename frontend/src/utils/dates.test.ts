import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  formatAbsolute,
  formatDateOnly,
  formatRelativeShort,
  formatRelative,
  formatCompact,
  formatShortDateTime,
  formatLogTime,
  formatBucketDate,
  formatWeekday,
} from './dates';

describe('formatAbsolute', () => {
  it('formats a valid ISO timestamp into a human-readable string', () => {
    const result = formatAbsolute('2024-06-15T10:30:00Z');
    expect(result).toContain('2024');
    expect(result).toContain('Jun');
    expect(result).toContain('15');
  });

  it('returns "—" for null input', () => {
    expect(formatAbsolute(null)).toBe('—');
  });

  it('returns "—" for undefined input', () => {
    expect(formatAbsolute(undefined)).toBe('—');
  });

  it('returns "—" for empty string input', () => {
    expect(formatAbsolute('')).toBe('—');
  });

  it('returns "—" for an invalid date string', () => {
    expect(formatAbsolute('not-a-date')).toBe('—');
  });
});

describe('formatDateOnly', () => {
  it('formats a valid ISO timestamp as date only (no time)', () => {
    const result = formatDateOnly('2024-06-15T10:30:00Z');
    expect(result).toContain('Jun');
    expect(result).toContain('15');
    expect(result).toContain('2024');
    // Should NOT contain time-related characters like ":"
    expect(result).not.toMatch(/\d{2}:\d{2}/);
  });

  it('returns "—" for null input', () => {
    expect(formatDateOnly(null)).toBe('—');
  });

  it('returns "—" for invalid date', () => {
    expect(formatDateOnly('garbage')).toBe('—');
  });
});

describe('formatRelativeShort', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns a short relative time for a recent timestamp', () => {
    // Mock Date.now to 30 minutes after the timestamp
    const base = new Date('2024-06-15T10:30:00Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(base + 30 * 60_000);
    expect(formatRelativeShort('2024-06-15T10:30:00Z')).toBe('30m ago');
  });

  it('returns hours for timestamps between 1-24 hours ago', () => {
    const base = new Date('2024-06-15T10:30:00Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(base + 3 * 60 * 60_000);
    expect(formatRelativeShort('2024-06-15T10:30:00Z')).toBe('3h ago');
  });

  it('returns days for timestamps more than 24 hours ago', () => {
    const base = new Date('2024-06-15T10:30:00Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(base + 48 * 60 * 60_000);
    expect(formatRelativeShort('2024-06-15T10:30:00Z')).toBe('2d ago');
  });

  it('returns "—" for null input', () => {
    expect(formatRelativeShort(null)).toBe('—');
  });
});

describe('formatRelative', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns a verbose relative time', () => {
    const base = new Date('2024-06-15T10:30:00Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(base + 5 * 60_000);
    expect(formatRelative('2024-06-15T10:30:00Z')).toBe('5 minutes ago');
  });

  it('uses singular form for 1 unit', () => {
    const base = new Date('2024-06-15T10:30:00Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(base + 1 * 60_000);
    expect(formatRelative('2024-06-15T10:30:00Z')).toBe('1 minute ago');
  });

  it('returns "just now" for very recent timestamps', () => {
    const base = new Date('2024-06-15T10:30:00Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(base + 30_000);
    expect(formatRelative('2024-06-15T10:30:00Z')).toBe('just now');
  });

  it('returns "—" for null input', () => {
    expect(formatRelative(null)).toBe('—');
  });
});

describe('formatCompact', () => {
  it('formats as a compact date/time string with seconds', () => {
    const result = formatCompact('2024-06-15T10:30:45Z');
    // Should contain date and time components
    expect(result).toMatch(/\d{2}\/\d{2}\/\d{4}/);
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it('returns "—" for null input', () => {
    expect(formatCompact(null)).toBe('—');
  });

  it('returns "—" for invalid date', () => {
    expect(formatCompact('not-a-date')).toBe('—');
  });
});

describe('formatShortDateTime', () => {
  it('formats as a short date/time string', () => {
    const result = formatShortDateTime('2024-06-15T10:30:00Z');
    expect(result).toContain('Jun');
    expect(result).toContain('15');
  });

  it('returns "—" for null input', () => {
    expect(formatShortDateTime(null)).toBe('—');
  });
});

describe('formatLogTime', () => {
  it('formats as time-only string', () => {
    const result = formatLogTime('2024-06-15T10:30:45Z');
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it('returns "—" for null input', () => {
    expect(formatLogTime(null)).toBe('—');
  });
});

describe('formatBucketDate', () => {
  it('formats as a locale date string', () => {
    const result = formatBucketDate('2024-06-15T10:30:00Z');
    expect(result).toContain('2024');
    expect(result).toContain('15');
  });

  it('returns "—" for null input', () => {
    expect(formatBucketDate(null)).toBe('—');
  });
});

describe('formatWeekday', () => {
  it('returns a short weekday name', () => {
    // 2024-06-15 is a Saturday
    const result = formatWeekday('2024-06-15T10:30:00Z');
    expect(result).toBe('Sat');
  });

  it('returns "—" for null input', () => {
    expect(formatWeekday(null)).toBe('—');
  });

  it('returns "—" for invalid date', () => {
    expect(formatWeekday('garbage')).toBe('—');
  });
});
