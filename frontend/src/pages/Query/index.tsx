import { useState, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { runQuery, listTemplates, createTemplate } from '../../api/query';
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
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set(['audit_events', 'detections', 'workflow_runs']));
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);
  const [showHistory, setShowHistory] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
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
