import { describe, it, expect } from 'vitest';
import { analyzeFailurePattern, getRemediationSuggestions } from './remediationGuidance';
import type { WorkflowRunRecord } from '../../api/workflowMetrics';

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeRun(conclusion: string, runId: string | null = 'run-1'): WorkflowRunRecord {
  return {
    run_id: runId,
    started_at: '2024-06-07T10:00:00Z',
    conclusion,
    duration_seconds: 120,
  };
}

// ── analyzeFailurePattern ────────────────────────────────────────────────────

describe('analyzeFailurePattern', () => {
  it('returns zeros and summary for empty runs', () => {
    const result = analyzeFailurePattern([]);
    expect(result.totalRuns).toBe(0);
    expect(result.failedRuns).toBe(0);
    expect(result.failureRate).toBe(0);
    expect(result.consecutiveFailures).toBe(0);
    expect(result.summary).toContain('No runs found');
  });

  it('counts all failures when every run failed', () => {
    const runs = [makeRun('failure'), makeRun('failure'), makeRun('failure')];
    const result = analyzeFailurePattern(runs);
    expect(result.totalRuns).toBe(3);
    expect(result.failedRuns).toBe(3);
    expect(result.failureRate).toBe(100);
    expect(result.consecutiveFailures).toBe(3);
    expect(result.summary).toContain('completely broken');
  });

  it('counts timed_out as failures', () => {
    const runs = [makeRun('timed_out'), makeRun('timed_out')];
    const result = analyzeFailurePattern(runs);
    expect(result.failedRuns).toBe(2);
    expect(result.failureRate).toBe(100);
  });

  it('returns zero failures when all succeed', () => {
    const runs = [makeRun('success'), makeRun('success'), makeRun('success')];
    const result = analyzeFailurePattern(runs);
    expect(result.failedRuns).toBe(0);
    expect(result.failureRate).toBe(0);
    expect(result.consecutiveFailures).toBe(0);
    expect(result.summary).toContain('All 3 recent runs succeeded');
  });

  it('counts consecutive failures from most recent', () => {
    // Most recent first: fail, fail, success, fail
    const runs = [makeRun('failure'), makeRun('failure'), makeRun('success'), makeRun('failure')];
    const result = analyzeFailurePattern(runs);
    expect(result.consecutiveFailures).toBe(2);
    expect(result.failedRuns).toBe(3);
    expect(result.totalRuns).toBe(4);
    expect(result.failureRate).toBe(75);
  });

  it('handles mixed failure and timed_out in streak', () => {
    const runs = [makeRun('timed_out'), makeRun('failure'), makeRun('success')];
    const result = analyzeFailurePattern(runs);
    expect(result.consecutiveFailures).toBe(2);
  });

  it('stops streak at first success', () => {
    const runs = [makeRun('success'), makeRun('failure'), makeRun('failure')];
    const result = analyzeFailurePattern(runs);
    expect(result.consecutiveFailures).toBe(0);
  });

  it('includes streak info in summary when consecutiveFailures > 1', () => {
    const runs = [makeRun('failure'), makeRun('failure'), makeRun('success')];
    const result = analyzeFailurePattern(runs);
    expect(result.summary).toContain('last 2 consecutive runs all failed');
  });

  it('rounds failure rate to nearest integer', () => {
    // 1 of 3 = 33.33...%
    const runs = [makeRun('failure'), makeRun('success'), makeRun('success')];
    const result = analyzeFailurePattern(runs);
    expect(result.failureRate).toBe(33);
  });
});

// ── getRemediationSuggestions ────────────────────────────────────────────────

describe('getRemediationSuggestions', () => {
  it('returns failure-specific suggestions for "failure" conclusion', () => {
    const pattern = analyzeFailurePattern([makeRun('failure'), makeRun('failure')]);
    const suggestions = getRemediationSuggestions('failure', pattern);
    expect(suggestions.length).toBeGreaterThanOrEqual(3);
    expect(suggestions.some((s) => s.title.includes('code changes'))).toBe(true);
    expect(suggestions.some((s) => s.title.includes('build and test logs'))).toBe(true);
    expect(suggestions.some((s) => s.title.includes('secrets'))).toBe(true);
  });

  it('returns timeout-specific suggestions for "timed_out" conclusion', () => {
    const pattern = analyzeFailurePattern([makeRun('timed_out'), makeRun('timed_out')]);
    const suggestions = getRemediationSuggestions('timed_out', pattern);
    expect(suggestions.some((s) => s.title.includes('timeout'))).toBe(true);
    expect(suggestions.some((s) => s.title.includes('infinite loops'))).toBe(true);
    expect(suggestions.some((s) => s.title.includes('runner resource'))).toBe(true);
  });

  it('suggests disabling workflow when failure rate is 100% with >= 3 runs', () => {
    const pattern = analyzeFailurePattern([
      makeRun('failure'),
      makeRun('failure'),
      makeRun('failure'),
    ]);
    const suggestions = getRemediationSuggestions('failure', pattern);
    expect(suggestions.some((s) => s.title.includes('disabling'))).toBe(true);
  });

  it('does NOT suggest disabling when failure rate is below 100%', () => {
    const pattern = analyzeFailurePattern([
      makeRun('failure'),
      makeRun('success'),
      makeRun('failure'),
    ]);
    const suggestions = getRemediationSuggestions('failure', pattern);
    expect(suggestions.some((s) => s.title.includes('disabling'))).toBe(false);
  });

  it('suggests escalation when consecutive failures >= 5', () => {
    const runs = Array.from({ length: 5 }, () => makeRun('failure'));
    const pattern = analyzeFailurePattern(runs);
    const suggestions = getRemediationSuggestions('failure', pattern);
    expect(suggestions.some((s) => s.title.includes('Escalate'))).toBe(true);
  });

  it('returns fallback suggestion for unknown conclusion with no failures', () => {
    const pattern = analyzeFailurePattern([makeRun('success')]);
    const suggestions = getRemediationSuggestions('cancelled', pattern);
    expect(suggestions.length).toBeGreaterThanOrEqual(1);
    expect(suggestions.some((s) => s.title.includes('Investigate'))).toBe(true);
  });

  it('returns non-empty array for every conclusion type', () => {
    for (const conclusion of ['failure', 'timed_out', 'success', 'cancelled', 'unknown']) {
      const pattern = analyzeFailurePattern([makeRun(conclusion)]);
      const suggestions = getRemediationSuggestions(conclusion, pattern);
      expect(suggestions.length).toBeGreaterThanOrEqual(1);
    }
  });
});
