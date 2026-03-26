import { useState, useRef } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { runQuery, listTemplates } from '../../api/query';
import type { QueryRunResponse } from '../../types/query';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Query.module.css';

const SCHEMA = [
  {
    table: 'audit_events',
    cols: [
      { name: 'id', type: 'uuid' },
      { name: 'action', type: 'text' },
      { name: 'actor', type: 'text' },
      { name: 'org', type: 'text' },
      { name: 'repo', type: 'text' },
      { name: 'actor_ip', type: 'inet' },
      { name: 'location', type: 'jsonb' },
      { name: 'created_at', type: 'tstz' },
      { name: 'data', type: 'jsonb' },
    ],
  },
  {
    table: 'detections',
    cols: [
      { name: 'id', type: 'uuid' },
      { name: 'rule_name', type: 'text' },
      { name: 'severity', type: 'text' },
      { name: 'detected_at', type: 'tstz' },
    ],
  },
  {
    table: 'workflow_runs',
    cols: [
      { name: 'run_id', type: 'bigint' },
      { name: 'workflow', type: 'text' },
      { name: 'conclusion', type: 'text' },
      { name: 'duration_s', type: 'int4' },
    ],
  },
];

const DEFAULT_SQL = `-- Actors with logins from 2+ countries in a single day
SELECT
  actor,
  COUNT(DISTINCT location->>'country_code') AS country_count,
  array_agg(DISTINCT location->>'country_code') AS countries,
  MIN(created_at) AS first_seen,
  MAX(created_at) AS last_seen
FROM audit_events
WHERE action = 'user.login'
  AND created_at >= NOW() - INTERVAL '1 day'
GROUP BY actor
HAVING COUNT(DISTINCT location->>'country_code') > 1;`;

export function QueryPage() {
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [results, setResults] = useState<QueryRunResponse | null>(null);
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set(['audit_events', 'detections', 'workflow_runs']));
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: templates } = useQuery({
    queryKey: ['query-templates'],
    queryFn: listTemplates,
  });

  const runMutation = useMutation({
    mutationFn: () => runQuery({ sql }),
    onSuccess: (data) => setResults(data),
  });

  const lines = sql.split('\n');

  function toggleTable(name: string) {
    setExpandedTables((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Query Explorer</div>
      <div className={styles.pageSub}>Write SQL against the audit events database</div>

      <div className={styles.queryLayout}>
        {/* Schema tree */}
        <div className={styles.schemaTree}>
          <div className={styles.schemaTitle}>Schema</div>
          {SCHEMA.map((s) => (
            <div key={s.table}>
              <div className={styles.schemaTable} onClick={() => toggleTable(s.table)}>
                {expandedTables.has(s.table) ? '▼' : '▶'} {s.table}
              </div>
              {expandedTables.has(s.table) && s.cols.map((c) => (
                <div key={c.name} className={styles.schemaCol}>
                  <span className={styles.schemaType}>{c.type}</span>&nbsp;{c.name}
                </div>
              ))}
            </div>
          ))}

          {templates && templates.length > 0 && (
            <>
              <div className={styles.schemaTitle} style={{ marginTop: 16 }}>Templates</div>
              {templates.map((t) => (
                <div
                  key={t.id}
                  className={styles.schemaTable}
                  onClick={() => setSql(t.sql)}
                  title={t.description ?? undefined}
                >
                  {t.name}
                </div>
              ))}
            </>
          )}
        </div>

        {/* Editor */}
        <div className={styles.editorWrap}>
          <div className={styles.editorFile}>
            <div className={styles.editorToolbar}>
              <span className={styles.editorFilename}>query.sql</span>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                <Button size="sm" variant="primary" onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
                  {runMutation.isPending ? '…' : '▶ Run'}
                </Button>
                <Button size="sm">Save</Button>
                <Button size="sm">History</Button>
              </div>
            </div>
            <div className={styles.editorBody}>
              <div className={styles.editorGutter}>
                {lines.map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              <textarea
                ref={textareaRef}
                className={styles.editorCode}
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                spellCheck={false}
                rows={lines.length}
              />
            </div>
          </div>

          {runMutation.isError && (
            <ErrorBanner message="Query failed" onRetry={() => runMutation.mutate()} />
          )}

          {runMutation.isPending && <Spinner />}

          {results && (
            <>
              <div className={styles.resultsMeta}>
                {results.row_count} row{results.row_count !== 1 ? 's' : ''} · {results.execution_ms}ms
                {results.truncated && <span style={{ color: 'var(--attention)' }}> (truncated)</span>}
              </div>
              <div className={styles.resultsTable}>
                <table>
                  <thead>
                    <tr>{results.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {results.rows.map((row, ri) => (
                      <tr key={ri}>
                        {row.map((cell, ci) => (
                          <td key={ci}>{String(cell ?? '')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
