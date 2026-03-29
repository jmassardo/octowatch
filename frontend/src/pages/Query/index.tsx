import { useState, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { runQuery, listTemplates, createTemplate } from '../../api/query';
import type { QueryRunResponse } from '../../types/query';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Query.module.css';

const SCHEMA = [
  {
    table: 'events',
    cols: [
      { name: 'id', type: 'bigint' },
      { name: 'action', type: 'text' },
      { name: 'namespace', type: 'text' },
      { name: 'actor', type: 'text' },
      { name: 'org', type: 'text' },
      { name: 'repo', type: 'text' },
      { name: 'source_ip', type: 'inet' },
      { name: 'geo_country_code', type: 'text' },
      { name: 'geo_city', type: 'text' },
      { name: 'created_at', type: 'tstz' },
      { name: 'data', type: 'jsonb' },
    ],
  },
  {
    table: 'detections',
    cols: [
      { name: 'id', type: 'bigint' },
      { name: 'title', type: 'text' },
      { name: 'severity', type: 'text' },
      { name: 'status', type: 'text' },
      { name: 'actor', type: 'text' },
      { name: 'org', type: 'text' },
      { name: 'repo', type: 'text' },
      { name: 'triggered_at', type: 'tstz' },
    ],
  },
  {
    table: 'events_hourly',
    cols: [
      { name: 'bucket_hour', type: 'tstz' },
      { name: 'org', type: 'text' },
      { name: 'namespace', type: 'text' },
      { name: 'action', type: 'text' },
      { name: 'event_count', type: 'bigint' },
    ],
  },
  {
    table: 'events_daily_actor',
    cols: [
      { name: 'bucket_day', type: 'tstz' },
      { name: 'actor', type: 'text' },
      { name: 'org', type: 'text' },
      { name: 'namespace', type: 'text' },
      { name: 'event_count', type: 'bigint' },
    ],
  },
  {
    table: 'detections_daily',
    cols: [
      { name: 'bucket_day', type: 'tstz' },
      { name: 'severity', type: 'text' },
      { name: 'status', type: 'text' },
      { name: 'detection_count', type: 'bigint' },
    ],
  },
];

const DEFAULT_SQL = `-- Actors with logins from 2+ countries in a single day
SELECT
  actor,
  COUNT(DISTINCT geo_country_code) AS country_count,
  array_agg(DISTINCT geo_country_code) AS countries,
  MIN(created_at) AS first_seen,
  MAX(created_at) AS last_seen
FROM events
WHERE action = 'user.login'
  AND created_at >= NOW() - INTERVAL '1 day'
GROUP BY actor
HAVING COUNT(DISTINCT geo_country_code) > 1`;

// --- SQL Syntax Highlighting ---

const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'GROUP', 'BY', 'HAVING', 'AND', 'OR', 'AS',
  'DISTINCT', 'ORDER', 'LIMIT', 'OFFSET', 'INSERT', 'INTO', 'VALUES',
  'UPDATE', 'SET', 'DELETE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER',
  'ON', 'IN', 'NOT', 'NULL', 'IS', 'LIKE', 'BETWEEN', 'CASE', 'WHEN',
  'THEN', 'ELSE', 'END', 'INTERVAL', 'TRUE', 'FALSE', 'ASC', 'DESC',
  'UNION', 'ALL', 'EXISTS', 'WITH', 'OVER', 'PARTITION',
]);

const SQL_FUNCTIONS = new Set([
  'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ARRAY_AGG', 'STRING_AGG',
  'COALESCE', 'NULLIF', 'CAST', 'NOW', 'DATE_TRUNC', 'EXTRACT',
  'LOWER', 'UPPER', 'TRIM', 'SUBSTRING', 'LENGTH', 'CONCAT',
  'ROW_NUMBER', 'RANK', 'DENSE_RANK',
]);

const COLUMN_NAMES = new Set(SCHEMA.flatMap((s) => s.cols.map((c) => c.name)));

type TokenType = 'keyword' | 'function' | 'column' | 'string' | 'comment' | 'plain';

interface SqlToken {
  type: TokenType;
  value: string;
}

function tokenizeSql(sql: string): SqlToken[] {
  const tokens: SqlToken[] = [];
  let i = 0;

  while (i < sql.length) {
    // Comments: -- to end of line
    if (sql[i] === '-' && i + 1 < sql.length && sql[i + 1] === '-') {
      const end = sql.indexOf('\n', i);
      const value = end === -1 ? sql.slice(i) : sql.slice(i, end);
      tokens.push({ type: 'comment', value });
      i += value.length;
      continue;
    }

    // String literals: '...' (with '' escape handling)
    if (sql[i] === "'") {
      let j = i + 1;
      while (j < sql.length) {
        if (sql[j] === "'") {
          if (j + 1 < sql.length && sql[j + 1] === "'") {
            j += 2;
          } else {
            break;
          }
        } else {
          j++;
        }
      }
      tokens.push({ type: 'string', value: sql.slice(i, j + 1) });
      i = j + 1;
      continue;
    }

    // Words: identifiers, keywords, functions
    if (/[a-zA-Z_]/.test(sql[i])) {
      let j = i;
      while (j < sql.length && /[a-zA-Z0-9_]/.test(sql[j])) j++;
      const word = sql.slice(i, j);
      const upper = word.toUpperCase();

      if (SQL_KEYWORDS.has(upper)) {
        tokens.push({ type: 'keyword', value: word });
      } else if (SQL_FUNCTIONS.has(upper)) {
        tokens.push({ type: 'function', value: word });
      } else if (COLUMN_NAMES.has(word)) {
        tokens.push({ type: 'column', value: word });
      } else {
        tokens.push({ type: 'plain', value: word });
      }
      i = j;
      continue;
    }

    // Other characters (operators, whitespace, punctuation)
    let j = i;
    while (j < sql.length && !/[a-zA-Z_'-]/.test(sql[j])) {
      j++;
    }
    if (j === i) {
      tokens.push({ type: 'plain', value: sql[i] });
      i++;
    } else {
      tokens.push({ type: 'plain', value: sql.slice(i, j) });
      i = j;
    }
  }

  return tokens;
}

const TOKEN_STYLES: Record<TokenType, string | undefined> = {
  keyword: styles.sqlKw,
  function: styles.sqlFn,
  column: styles.sqlCol,
  string: styles.sqlLit,
  comment: styles.sqlCmt,
  plain: undefined,
};

function renderHighlightedSql(sqlText: string) {
  return tokenizeSql(sqlText).map((token, i) => {
    const cls = TOKEN_STYLES[token.type];
    if (cls) {
      return (
        <span key={i} className={cls}>
          {token.value}
        </span>
      );
    }
    return token.value;
  });
}

// --- Query History ---

const HISTORY_KEY = 'octowatch:query-history';
const MAX_HISTORY = 20;

interface HistoryEntry {
  sql: string;
  timestamp: string;
}

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(entries: HistoryEntry[]): void {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, MAX_HISTORY)));
}

export function QueryPage() {
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [results, setResults] = useState<QueryRunResponse | null>(null);
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set(['events', 'detections', 'events_hourly', 'events_daily_actor', 'detections_daily']));
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);
  const [showHistory, setShowHistory] = useState(false);
  const [showExecModal, setShowExecModal] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const resultsTableRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: templates } = useQuery({
    queryKey: ['query-templates'],
    queryFn: listTemplates,
  });

  const runMutation = useMutation({
    mutationFn: (runSql: string) => runQuery({ sql: runSql }),
    onSuccess: (data, runSql) => {
      setResults(data);
      setHistory((prev) => {
        const entry: HistoryEntry = { sql: runSql, timestamp: new Date().toISOString() };
        const updated = [entry, ...prev.filter((h) => h.sql !== runSql)].slice(0, MAX_HISTORY);
        saveHistory(updated);
        return updated;
      });
    },
  });

  const saveMutation = useMutation({
    mutationFn: (name: string) => createTemplate({ name, sql }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['query-templates'] });
    },
  });

  const lines = sql.split('\n');

  function handleSave() {
    const name = window.prompt('Query name:', 'Untitled query');
    if (name) {
      saveMutation.mutate(name);
    }
  }

  function handleHistorySelect(entry: HistoryEntry) {
    setSql(entry.sql);
    setShowHistory(false);
  }

  function handleEditorScroll(e: React.UIEvent<HTMLTextAreaElement>) {
    if (highlightRef.current) {
      highlightRef.current.scrollTop = e.currentTarget.scrollTop;
      highlightRef.current.scrollLeft = e.currentTarget.scrollLeft;
    }
  }

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
              <div className={styles.toolbarActions}>
                <Button size="sm" variant="primary" onClick={() => runMutation.mutate(sql)} disabled={runMutation.isPending}>
                  {runMutation.isPending ? '…' : '▶ Run'}
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? '…' : 'Save'}
                </Button>
                <div className={styles.historyWrap}>
                  <Button size="sm" onClick={() => setShowHistory((v) => !v)}>
                    History
                  </Button>
                  {showHistory && (
                    <>
                      <div className={styles.historyBackdrop} onClick={() => setShowHistory(false)} />
                      <div className={styles.historyDropdown}>
                        {history.length === 0 ? (
                          <div className={styles.historyEmpty}>No queries run yet</div>
                        ) : (
                          history.map((entry, i) => (
                            <div key={i} className={styles.historyItem} onClick={() => handleHistorySelect(entry)}>
                              <div className={styles.historySql}>
                                {entry.sql.slice(0, 80)}
                                {entry.sql.length > 80 ? '…' : ''}
                              </div>
                              <div className={styles.historyTime}>
                                {new Date(entry.timestamp).toLocaleString()}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className={styles.editorBody}>
              <div className={styles.editorGutter}>
                {lines.map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              <div className={styles.editorCodeWrap}>
                <pre
                  ref={highlightRef}
                  className={styles.editorHighlight}
                  aria-hidden="true"
                >
                  {renderHighlightedSql(sql)}
                </pre>
                <textarea
                  ref={textareaRef}
                  className={styles.editorCode}
                  value={sql}
                  onChange={(e) => setSql(e.target.value)}
                  onScroll={handleEditorScroll}
                  spellCheck={false}
                  rows={lines.length}
                />
              </div>
            </div>
          </div>

          {runMutation.isError && (
            <ErrorBanner message="Query failed" onRetry={() => runMutation.mutate(sql)} />
          )}

          {runMutation.isPending && <Spinner />}

          {results && (
            <>
              <div className={styles.resultsMeta}>
                <span
                  className={styles.clickableMeta}
                  role="button"
                  tabIndex={0}
                  onClick={() => resultsTableRef.current?.scrollIntoView({ behavior: 'smooth' })}
                  onKeyDown={(e) => { if (e.key === 'Enter') resultsTableRef.current?.scrollIntoView({ behavior: 'smooth' }); }}
                >
                  {results.row_count} row{results.row_count !== 1 ? 's' : ''}
                </span>
                {' · '}
                <span
                  className={styles.clickableMeta}
                  role="button"
                  tabIndex={0}
                  onClick={() => setShowExecModal(true)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setShowExecModal(true); }}
                >
                  {results.execution_ms}ms
                </span>
                {results.truncated && <span style={{ color: 'var(--attention)' }}> (truncated)</span>}
              </div>
              <div className={styles.resultsTable} ref={resultsTableRef}>
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

      {results && (
        <Modal open={showExecModal} onClose={() => setShowExecModal(false)} title="Query Execution Details" width={420}>
          <dl className={styles.execDetail}>
            <dt>Query ID</dt>
            <dd>{results.query_id}</dd>
            <dt>Execution time</dt>
            <dd>{results.execution_ms} ms</dd>
            <dt>Rows returned</dt>
            <dd>{results.row_count}</dd>
            <dt>Truncated</dt>
            <dd>{results.truncated ? 'Yes' : 'No'}</dd>
          </dl>
          <p className={styles.execNote}>
            Additional metrics like rows scanned and bytes processed require query engine instrumentation.
          </p>
        </Modal>
      )}
    </div>
  );
}
