import { useMutation } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { backtestRule } from '../../api/rules';
import type { BacktestResult } from '../../api/rules';
import type { RuleResponse } from '../../types/detections';
import { Button } from '../../components/primitives/Button';
import { DataTable } from '../../components/primitives/DataTable';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Rules.module.css';

function toDateInput(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function createInitialDates() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - 6);
  return { start: toDateInput(start), end: toDateInput(end) };
}

export function BacktestPanel({ rule }: { rule: RuleResponse }) {
  const initialDates = useMemo(() => createInitialDates(), []);
  const [startDate, setStartDate] = useState(initialDates.start);
  const [endDate, setEndDate] = useState(initialDates.end);
  const [maxResults, setMaxResults] = useState('1000');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      backtestRule(rule.id, {
        start_date: startDate,
        end_date: endDate,
        max_results: Number(maxResults),
      }),
    onSuccess: (data) => {
      setResult(data);
      setValidationError(null);
    },
  });

  function handleRunBacktest() {
    if (!startDate || !endDate) {
      setValidationError('Start and end dates are required.');
      return;
    }

    const start = new Date(`${startDate}T00:00:00Z`);
    const end = new Date(`${endDate}T00:00:00Z`);
    const dateDiffDays = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);

    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      setValidationError('Enter a valid date range.');
      return;
    }
    if (end < start) {
      setValidationError('End date must be on or after the start date.');
      return;
    }
    if (dateDiffDays > 30) {
      setValidationError('Backtests support a maximum 30 day range.');
      return;
    }

    const parsedMaxResults = Number(maxResults);
    if (!Number.isInteger(parsedMaxResults) || parsedMaxResults <= 0) {
      setValidationError('Max results must be a positive whole number.');
      return;
    }

    mutation.mutate();
  }

  return (
    <div className={styles.backtestPanel}>
      <div className={styles.backtestControls}>
        <div className={styles.formRow}>
          <label className={styles.formLabel} htmlFor="backtest-start-date">
            Start date
          </label>
          <input
            id="backtest-start-date"
            className={styles.formInput}
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel} htmlFor="backtest-end-date">
            End date
          </label>
          <input
            id="backtest-end-date"
            className={styles.formInput}
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </div>
        <div className={styles.formRow}>
          <label className={styles.formLabel} htmlFor="backtest-max-results">
            Max results
          </label>
          <input
            id="backtest-max-results"
            className={styles.formInput}
            type="number"
            min={1}
            value={maxResults}
            onChange={(event) => setMaxResults(event.target.value)}
          />
        </div>
        <Button
          type="button"
          variant="primary"
          onClick={handleRunBacktest}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? 'Running…' : 'Run Backtest'}
        </Button>
      </div>

      {validationError && <ErrorBanner message={validationError} />}
      {mutation.isError && (
        <ErrorBanner message="Failed to run backtest" onRetry={handleRunBacktest} />
      )}

      {result && (
        <>
          <div className={styles.backtestSummary}>
            {result.total_matches} matches in {result.events_scanned} events scanned (
            {result.duration_ms} ms)
          </div>
          {result.capped && (
            <div className={styles.backtestWarning}>Results capped at {Number(maxResults)}</div>
          )}
          <DataTable
            columns={[
              {
                key: 'timestamp',
                header: 'Timestamp',
                sortable: true,
                sortValue: (match) => match.timestamp,
                render: (match) => match.timestamp,
              },
              { key: 'actor', header: 'Actor', render: (match) => match.actor ?? '—' },
              { key: 'action', header: 'Action', render: (match) => match.action },
              { key: 'org', header: 'Org', render: (match) => match.org ?? '—' },
              { key: 'repo', header: 'Repo', render: (match) => match.repo ?? '—' },
              {
                key: 'matched_conditions',
                header: 'Matched Conditions',
                render: (match) => match.matched_conditions.join(', ') || '—',
              },
            ]}
            data={result.matches}
            rowKey={(match) => `${match.event_id}-${match.timestamp}`}
            emptyMessage="No matches found for the selected range"
          />
        </>
      )}
    </div>
  );
}
