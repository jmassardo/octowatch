import { useState, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { runQuery, listTemplates, createTemplate } from '../../api/query';
import { translateNLQuery } from '../../api/nlQuery';
import type { NLInterpretation } from '../../api/nlQuery';
import type { QueryRunResponse } from '../../types/query';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { formatAbsolute } from '../../utils/dates';
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
  'SELECT',
  'FROM',
  'WHERE',
  'GROUP',
  'BY',
  'HAVING',
  'AND',
  'OR',
  'AS',
  'DISTINCT',
  'ORDER',
  'LIMIT',
  'OFFSET',
  'INSERT',
  'INTO',
  'VALUES',
  'UPDATE',
  'SET',
  'DELETE',
  'JOIN',
  'LEFT',
  'RIGHT',
  'INNER',
  'OUTER',
  'ON',
  'IN',
  'NOT',
  'NULL',
  'IS',
  'LIKE',
  'BETWEEN',
  'CASE',
  'WHEN',
  'THEN',
  'ELSE',
  'END',
  'INTERVAL',
  'TRUE',
  'FALSE',
  'ASC',
  'DESC',
  'UNION',
  'ALL',
  'EXISTS',
  'WITH',
  'OVER',
  'PARTITION',
]);

const SQL_FUNCTIONS = new Set([
  'COUNT',
  'SUM',
  'AVG',
  'MIN',
  'MAX',
  'ARRAY_AGG',
  'STRING_AGG',
  'COALESCE',
  'NULLIF',
  'CAST',
  'NOW',
  'DATE_TRUNC',
  'EXTRACT',
  'LOWER',
  'UPPER',
  'TRIM',
  'SUBSTRING',
  'LENGTH',
  'CONCAT',
  'ROW_NUMBER',
  'RANK',
  'DENSE_RANK',
]);

// --- Client-side SQL Validation ---

const TABLE_NAMES = new Set(SCHEMA.map((s) => s.table.toLowerCase()));
const ALL_COLUMNS = new Map<string, Set<string>>();
for (const s of SCHEMA) {
  ALL_COLUMNS.set(s.table.toLowerCase(), new Set(s.cols.map((c) => c.name.toLowerCase())));
}
const EVERY_COLUMN = new Set(SCHEMA.flatMap((s) => s.cols.map((c) => c.name.toLowerCase())));

// Backend-aligned allowed functions (lowercase)
const VALID_FUNCTIONS = new Set([
  'count',
  'sum',
  'avg',
  'min',
  'max',
  'string_agg',
  'array_agg',
  'bool_or',
  'bool_and',
  'date_trunc',
  'time_bucket',
  'to_char',
  'to_timestamp',
  'date_part',
  'extract',
  'now',
  'timezone',
  'age',
  'date',
  'make_interval',
  'justify_interval',
  'lower',
  'upper',
  'length',
  'substr',
  'substring',
  'regexp_replace',
  'regexp_matches',
  'concat',
  'trim',
  'btrim',
  'ltrim',
  'rtrim',
  'replace',
  'left',
  'right',
  'position',
  'strpos',
  'split_part',
  'coalesce',
  'nullif',
  'greatest',
  'least',
  'abs',
  'ceil',
  'floor',
  'round',
  'trunc',
  'jsonb_extract_path_text',
  'jsonb_array_elements',
  'row_number',
  'rank',
  'dense_rank',
  'lag',
  'lead',
  'first_value',
  'last_value',
  'ntile',
  'percent_rank',
  'cume_dist',
  'cast',
  'unnest',
  'generate_series',
]);

interface ValidationResult {
  valid: boolean;
  error: string;
}

function validateSqlLocally(sql: string): ValidationResult {
  const trimmed = sql.trim().replace(/;+$/, '').trim();
  if (!trimmed) return { valid: true, error: '' };

  // Strip leading SQL comments before determining the first keyword
  const withoutLeadingComments = trimmed.replace(/^(\s*--[^\n]*\n)+/g, '').trim();
  if (!withoutLeadingComments) return { valid: true, error: '' };

  // 1. Check for write statements
  const firstWord = withoutLeadingComments.split(/\s+/)[0].toUpperCase();
  const writeStatements = [
    'INSERT',
    'UPDATE',
    'DELETE',
    'DROP',
    'ALTER',
    'CREATE',
    'TRUNCATE',
    'GRANT',
    'REVOKE',
  ];
  if (writeStatements.includes(firstWord)) {
    return { valid: false, error: `Only SELECT statements are permitted (found ${firstWord})` };
  }

  // 2. Check balanced parentheses
  let parenDepth = 0;
  let inString = false;
  let inComment = false;
  for (let i = 0; i < trimmed.length; i++) {
    const ch = trimmed[i];
    if (inComment) {
      if (ch === '\n') inComment = false;
      continue;
    }
    if (ch === '-' && i + 1 < trimmed.length && trimmed[i + 1] === '-') {
      inComment = true;
      continue;
    }
    if (ch === "'") {
      if (inString && i + 1 < trimmed.length && trimmed[i + 1] === "'") {
        i++; // skip escaped quote
        continue;
      }
      inString = !inString;
      continue;
    }
    if (inString) continue;
    if (ch === '(') parenDepth++;
    if (ch === ')') parenDepth--;
    if (parenDepth < 0) {
      return { valid: false, error: 'Unmatched closing parenthesis ")"' };
    }
  }
  if (parenDepth > 0) {
    return { valid: false, error: `Unmatched opening parenthesis — ${parenDepth} unclosed "("` };
  }
  if (inString) {
    return { valid: false, error: 'Unterminated string literal — missing closing quote' };
  }

  // 3. Extract and check table references (FROM / JOIN)
  const tablePattern = /\b(?:FROM|JOIN)\s+([a-zA-Z_]\w*)/gi;
  let match;
  const referencedTables: string[] = [];
  while ((match = tablePattern.exec(trimmed)) !== null) {
    const tbl = match[1].toLowerCase();
    referencedTables.push(tbl);
    if (!TABLE_NAMES.has(tbl)) {
      return {
        valid: false,
        error: `Table '${match[1]}' is not in allowed tables: ${[...TABLE_NAMES].sort().join(', ')}`,
      };
    }
  }

  // 4. Extract and check function calls
  const funcPattern = /\b([a-zA-Z_]\w*)\s*\(/g;
  while ((match = funcPattern.exec(trimmed)) !== null) {
    const fn = match[1].toLowerCase();
    // Skip SQL keywords that use parens (e.g., IN(...), EXISTS(...))
    if (SQL_KEYWORDS.has(fn.toUpperCase())) continue;
    // Skip type casts (e.g., INTERVAL, TIMESTAMP)
    if (
      [
        'interval',
        'timestamp',
        'date',
        'time',
        'integer',
        'bigint',
        'text',
        'boolean',
        'numeric',
        'float',
        'real',
        'double',
      ].includes(fn)
    )
      continue;
    if (!VALID_FUNCTIONS.has(fn)) {
      return { valid: false, error: `Function '${match[1]}' is not permitted` };
    }
  }

  // 5. Check for likely missing commas in SELECT list
  // Two consecutive column names without a comma suggests a missing comma
  const selectFromMatch = trimmed.match(/\bSELECT\b\s+([\s\S]*?)\bFROM\b/i);
  if (selectFromMatch) {
    const selectRaw = selectFromMatch[1]
      .replace(/--[^\n]*/g, ' ')
      .replace(/'[^']*'/g, ' ')
      .replace(/\b\w+\s*\([^)]*\)/g, ' ');
    const consecutivePattern = /\b([a-zA-Z_]\w*)\s+([a-zA-Z_]\w*)\b/g;
    let cm;
    while ((cm = consecutivePattern.exec(selectRaw)) !== null) {
      const first = cm[1].toLowerCase();
      const second = cm[2].toLowerCase();
      if (SQL_KEYWORDS.has(cm[1].toUpperCase()) || SQL_KEYWORDS.has(cm[2].toUpperCase())) continue;
      if (VALID_FUNCTIONS.has(first) || VALID_FUNCTIONS.has(second)) continue;
      if (EVERY_COLUMN.has(first) && EVERY_COLUMN.has(second)) {
        return { valid: false, error: `Possible missing comma between '${cm[1]}' and '${cm[2]}'` };
      }
    }
  }

  // 6. Check identifiers in SELECT list for unknown columns
  if (selectFromMatch) {
    const selectList = selectFromMatch[1];
    // Extract bare identifiers (not part of functions, not aliases after AS, not *)
    const identTokens = selectList
      .replace(/--[^\n]*/g, '') // strip comments
      .replace(/'[^']*'/g, '') // strip string literals
      .replace(/\b\w+\s*\([^)]*\)/g, '') // strip function calls (simple)
      .replace(/\bAS\s+\w+/gi, '') // strip aliases
      .replace(/\bDISTINCT\b/gi, '') // strip DISTINCT
      .split(/[,\s]+/)
      .map((t) => t.trim().toLowerCase())
      .filter((t) => t && /^[a-z_]\w*$/.test(t) && t !== '*');

    // Get columns available from referenced tables
    const availableCols = new Set<string>();
    if (referencedTables.length > 0) {
      for (const tbl of referencedTables) {
        const cols = ALL_COLUMNS.get(tbl);
        if (cols) cols.forEach((c) => availableCols.add(c));
      }
    } else {
      EVERY_COLUMN.forEach((c) => availableCols.add(c));
    }

    for (const ident of identTokens) {
      // Skip if it's a known keyword, function, or table name
      if (SQL_KEYWORDS.has(ident.toUpperCase())) continue;
      if (VALID_FUNCTIONS.has(ident)) continue;
      if (TABLE_NAMES.has(ident)) continue;
      // Skip numeric literals
      if (/^\d+$/.test(ident)) continue;

      if (!availableCols.has(ident)) {
        return {
          valid: false,
          error: `Column '${ident}' does not exist in ${referencedTables.length > 0 ? referencedTables.join(', ') : 'any table'}`,
        };
      }
    }
  }

  // 6. Check for missing SELECT keyword
  if (!firstWord || (firstWord !== 'SELECT' && firstWord !== 'WITH')) {
    return { valid: false, error: `Query must start with SELECT or WITH (found '${firstWord}')` };
  }

  return { valid: true, error: '' };
}

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
      } else if (EVERY_COLUMN.has(word.toLowerCase())) {
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

/** Extract the range of the problematic token from a validation error message */
function getErrorRange(sql: string, error: string): { start: number; end: number } | null {
  const patterns: RegExp[] = [
    /Table '([^']+)'/,
    /Function\(s\) not permitted: \['?([^'"\]]+)/,
    /Function '([^']+)' is not permitted/,
    /syntax error at or near "([^"]+)"/,
    /Statement type not permitted: (\w+)/,
    /Schema-qualified.*: ([^\s]+)/,
    /Column '([^']+)' does not exist/,
    /Possible missing comma between '([^']+)'/,
    // PostgreSQL runtime errors
    /column "(?:\w+\.)?(\w+)" must appear/,
    /column "(\w+)" does not exist/,
    /relation "(\w+)" does not exist/,
    /function (\w+)\(.*?\) does not exist/,
  ];

  for (const pat of patterns) {
    const m = error.match(pat);
    if (m) {
      const token = m[1];
      const sqlLower = sql.toLowerCase();
      const idx = sqlLower.indexOf(token.toLowerCase());
      if (idx !== -1) {
        return { start: idx, end: idx + token.length };
      }
    }
  }
  return null;
}

function renderHighlightedSql(sqlText: string, errorRange?: { start: number; end: number } | null) {
  const tokens = tokenizeSql(sqlText);
  const elements: React.ReactNode[] = [];
  let pos = 0;

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    const tokenStart = pos;
    const tokenEnd = pos + token.value.length;
    const cls = TOKEN_STYLES[token.type];

    if (errorRange && tokenStart < errorRange.end && tokenEnd > errorRange.start) {
      const overlapStart = Math.max(tokenStart, errorRange.start) - tokenStart;
      const overlapEnd = Math.min(tokenEnd, errorRange.end) - tokenStart;

      const before = token.value.slice(0, overlapStart);
      const errorPart = token.value.slice(overlapStart, overlapEnd);
      const after = token.value.slice(overlapEnd);

      if (before) {
        elements.push(
          cls ? (
            <span key={`${i}a`} className={cls}>
              {before}
            </span>
          ) : (
            before
          ),
        );
      }
      elements.push(
        <span key={`${i}e`} className={`${cls ?? ''} ${styles.errorUnderline}`.trim()}>
          {errorPart}
        </span>,
      );
      if (after) {
        elements.push(
          cls ? (
            <span key={`${i}z`} className={cls}>
              {after}
            </span>
          ) : (
            after
          ),
        );
      }
    } else if (cls) {
      elements.push(
        <span key={i} className={cls}>
          {token.value}
        </span>,
      );
    } else {
      elements.push(token.value);
    }
    pos = tokenEnd;
  }

  return elements;
}

// --- Validation & Autocomplete ---

type ValidationStatus = 'idle' | 'valid' | 'invalid';

type SuggestionKind = 'keyword' | 'function' | 'table' | 'column';

interface Suggestion {
  text: string;
  kind: SuggestionKind;
  label: string;
}

type SuggestionContext = 'table' | 'column' | 'general';

const IS_MAC = typeof navigator !== 'undefined' && /Mac/.test(navigator.userAgent);

/** Check if cursor position falls inside a string literal or comment token */
function isCursorInStringOrComment(sql: string, cursorPos: number): boolean {
  const tokens = tokenizeSql(sql);
  let pos = 0;
  for (const token of tokens) {
    const end = pos + token.value.length;
    if (cursorPos > pos && cursorPos <= end) {
      return token.type === 'string' || token.type === 'comment';
    }
    pos = end;
  }
  return false;
}

/** Extract partial word being typed at cursor position */
function getPartialWord(sql: string, cursorPos: number): string {
  let start = cursorPos;
  while (start > 0 && /[a-zA-Z0-9_]/.test(sql[start - 1])) {
    start--;
  }
  return sql.slice(start, cursorPos);
}

/** Determine what kind of suggestions to show based on the SQL keyword before cursor */
function getSuggestionContext(sql: string, cursorPos: number): SuggestionContext {
  const beforeCursor = sql.substring(0, cursorPos);
  const stripped = beforeCursor
    .replace(/[a-zA-Z0-9_]*$/, '')
    .trimEnd()
    .toUpperCase();

  if (stripped.endsWith('FROM') || stripped.endsWith('JOIN')) {
    return 'table';
  }

  if (
    stripped.endsWith('SELECT') ||
    stripped.endsWith(',') ||
    stripped.endsWith('WHERE') ||
    stripped.endsWith('AND') ||
    stripped.endsWith('OR') ||
    stripped.endsWith('BY') ||
    stripped.endsWith('ON') ||
    stripped.endsWith('HAVING')
  ) {
    return 'column';
  }

  return 'general';
}

/** Extract table names referenced in FROM / JOIN clauses */
function extractReferencedTables(sql: string): string[] {
  const knownTables = new Set(SCHEMA.map((s) => s.table.toLowerCase()));
  const found: string[] = [];
  const regex = /\b(?:FROM|JOIN)\s+(\w+)/gi;
  let match;
  while ((match = regex.exec(sql)) !== null) {
    const name = match[1].toLowerCase();
    if (knownTables.has(name) && !found.includes(name)) {
      found.push(name);
    }
  }
  return found;
}

/** Generate context-aware autocomplete suggestions */
function computeSuggestions(sql: string, cursorPos: number): Suggestion[] {
  if (isCursorInStringOrComment(sql, cursorPos)) return [];

  const partial = getPartialWord(sql, cursorPos);
  const context = getSuggestionContext(sql, cursorPos);
  const minChars = context === 'general' ? 2 : 1;

  if (partial.length < minChars) return [];

  const lower = partial.toLowerCase();
  const results: Suggestion[] = [];

  if (context === 'table') {
    for (const s of SCHEMA) {
      if (s.table.toLowerCase().startsWith(lower)) {
        results.push({ text: s.table, kind: 'table', label: 'TBL' });
      }
    }
  } else if (context === 'column') {
    const refTables = extractReferencedTables(sql);
    const tablesToSearch =
      refTables.length > 0
        ? SCHEMA.filter((s) => refTables.includes(s.table.toLowerCase()))
        : SCHEMA;

    const seen = new Set<string>();
    for (const table of tablesToSearch) {
      for (const col of table.cols) {
        if (col.name.toLowerCase().startsWith(lower) && !seen.has(col.name)) {
          seen.add(col.name);
          results.push({ text: col.name, kind: 'column', label: 'COL' });
        }
      }
    }
  } else {
    for (const kw of SQL_KEYWORDS) {
      if (kw.toLowerCase().startsWith(lower)) {
        results.push({ text: kw, kind: 'keyword', label: 'KW' });
      }
    }
    for (const fn of SQL_FUNCTIONS) {
      if (fn.toLowerCase().startsWith(lower)) {
        results.push({ text: fn, kind: 'function', label: 'FN' });
      }
    }
    for (const s of SCHEMA) {
      if (s.table.toLowerCase().startsWith(lower)) {
        results.push({ text: s.table, kind: 'table', label: 'TBL' });
      }
    }
    const seen = new Set<string>();
    for (const s of SCHEMA) {
      for (const col of s.cols) {
        if (col.name.toLowerCase().startsWith(lower) && !seen.has(col.name)) {
          seen.add(col.name);
          results.push({ text: col.name, kind: 'column', label: 'COL' });
        }
      }
    }
  }

  return results.slice(0, 8);
}

/** Calculate pixel position of cursor in textarea relative to viewport (fixed positioning) */
function getCursorPixelPosition(textarea: HTMLTextAreaElement): { top: number; left: number } {
  const cs = getComputedStyle(textarea);
  const lineHeight = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.7;
  const charWidth = parseFloat(cs.fontSize) * 0.6; // monospace approximation
  const paddingTop = parseFloat(cs.paddingTop) || 0;
  const paddingLeft = parseFloat(cs.paddingLeft) || 0;

  const textBeforeCursor = textarea.value.substring(0, textarea.selectionStart);
  const linesBeforeCursor = textBeforeCursor.split('\n');
  const row = linesBeforeCursor.length - 1;
  const col = linesBeforeCursor[linesBeforeCursor.length - 1].length;

  const rect = textarea.getBoundingClientRect();

  return {
    top: rect.top + paddingTop + row * lineHeight - textarea.scrollTop + lineHeight,
    left: rect.left + paddingLeft + col * charWidth - textarea.scrollLeft,
  };
}

/** Positioned autocomplete dropdown rendered via portal to avoid overflow clipping */
function SqlAutocomplete({
  items,
  activeIndex,
  position,
  partial,
  onAccept,
}: {
  items: readonly Suggestion[];
  activeIndex: number;
  position: { top: number; left: number };
  partial: string;
  onAccept: (text: string) => void;
}) {
  return createPortal(
    <div
      className={styles.acDropdown}
      style={{
        position: 'fixed',
        top: position.top,
        left: position.left,
      }}
      role="listbox"
    >
      {items.map((item, i) => (
        <div
          key={`${item.kind}-${item.text}`}
          className={`${styles.acItem}${i === activeIndex ? ` ${styles.acItemActive}` : ''}`}
          role="option"
          aria-selected={i === activeIndex}
          onMouseDown={(e) => {
            e.preventDefault();
            onAccept(item.text);
          }}
        >
          <span className={styles.acItemType}>{item.label}</span>
          <span>
            <span className={styles.acHighlight}>{item.text.slice(0, partial.length)}</span>
            {item.text.slice(partial.length)}
          </span>
        </div>
      ))}
    </div>,
    document.body,
  );
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
  const [expandedTables, setExpandedTables] = useState<Set<string>>(
    new Set(['events', 'detections', 'events_hourly', 'events_daily_actor', 'detections_daily']),
  );
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);
  const [showHistory, setShowHistory] = useState(false);
  const [showExecModal, setShowExecModal] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const resultsTableRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const [nlInput, setNlInput] = useState('');
  const [nlResults, setNlResults] = useState<NLInterpretation[]>([]);

  type QueryResultRow = Record<string, unknown>;

  const queryResultColumns: ColumnDef<QueryResultRow>[] = useMemo(() => {
    if (!results) return [];
    return results.columns.map((col) => ({
      key: col,
      header: col,
      sortable: true,
      filterable: true,
      sortValue: (row: QueryResultRow) => {
        const val = row[col];
        if (val == null) return '';
        if (typeof val === 'number') return val;
        return String(val).toLowerCase();
      },
      filterValue: (row: QueryResultRow) => String(row[col] ?? ''),
      render: (row: QueryResultRow) => String(row[col] ?? ''),
    }));
  }, [results]);

  const queryResultRows: QueryResultRow[] = useMemo(() => {
    if (!results) return [];
    return results.rows.map((row, ri) => {
      const obj: QueryResultRow = { __rowIndex: ri };
      results.columns.forEach((col, ci) => {
        obj[col] = row[ci];
      });
      return obj;
    });
  }, [results]);

  // Instant client-side validation — no API calls needed
  const localValidation = validateSqlLocally(sql);
  const validationStatus: ValidationStatus = !sql.trim()
    ? 'idle'
    : localValidation.valid
      ? 'valid'
      : 'invalid';
  const validationError = localValidation.error;
  const errorRange = validationStatus === 'invalid' ? getErrorRange(sql, validationError) : null;
  const [acItems, setAcItems] = useState<Suggestion[]>([]);
  const [acIndex, setAcIndex] = useState(0);
  const [acPosition, setAcPosition] = useState({ top: 0, left: 0 });
  const [acPartial, setAcPartial] = useState('');
  const cursorPosRef = useRef(0);
  const acDismissedRef = useRef(false);

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

  const nlMutation = useMutation({
    mutationFn: (query: string) => translateNLQuery({ query }),
    onSuccess: (data) => {
      setNlResults(data.interpretations);
    },
  });

  const handleNlSubmit = () => {
    const trimmed = nlInput.trim();
    if (trimmed) {
      nlMutation.mutate(trimmed);
    }
  };

  const handleNlSelect = (interpretation: NLInterpretation) => {
    setSql(interpretation.sql);
    setNlResults([]);
    setAcItems([]);
    setAcPartial('');
  };

  const lines = sql.split('\n');

  /** Update autocomplete suggestions inline in the event handler (not in an effect) */
  function updateAutocomplete(newSql: string, cursorPos: number) {
    if (acDismissedRef.current) {
      setAcItems([]);
      setAcPartial('');
      return;
    }
    const items = computeSuggestions(newSql, cursorPos);
    const partial = getPartialWord(newSql, cursorPos);
    setAcItems(items);
    setAcPartial(partial);
    setAcIndex(0);
    if (items.length > 0 && textareaRef.current) {
      setAcPosition(getCursorPixelPosition(textareaRef.current));
    }
  }

  function handleSqlChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const newSql = e.target.value;
    const cursorPos = e.target.selectionStart;
    setSql(newSql);
    cursorPosRef.current = cursorPos;
    acDismissedRef.current = false;
    updateAutocomplete(newSql, cursorPos);
  }

  function acceptSuggestion(text: string) {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const cursorPos = cursorPosRef.current;
    const partial = getPartialWord(sql, cursorPos);
    const start = cursorPos - partial.length;
    const newSql = sql.slice(0, start) + text + sql.slice(cursorPos);
    setSql(newSql);
    const newCursorPos = start + text.length;
    cursorPosRef.current = newCursorPos;
    setAcItems([]);
    setAcPartial('');
    setAcIndex(0);
    acDismissedRef.current = true;
    requestAnimationFrame(() => {
      textarea.focus();
      textarea.selectionStart = newCursorPos;
      textarea.selectionEnd = newCursorPos;
    });
  }

  function insertAtCursor(text: string) {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const pos = textarea.selectionStart ?? sql.length;
    const newSql = sql.slice(0, pos) + text + sql.slice(pos);
    setSql(newSql);
    setAcItems([]);
    setAcPartial('');
    const newPos = pos + text.length;
    cursorPosRef.current = newPos;
    requestAnimationFrame(() => {
      textarea.focus();
      textarea.selectionStart = newPos;
      textarea.selectionEnd = newPos;
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Ctrl/Cmd+Enter to run query
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      runMutation.mutate(sql);
      return;
    }

    // Arrow keys always control cursor — dismiss autocomplete if open
    if (
      e.key === 'ArrowUp' ||
      e.key === 'ArrowDown' ||
      e.key === 'ArrowLeft' ||
      e.key === 'ArrowRight'
    ) {
      if (acItems.length > 0) {
        setAcItems([]);
        acDismissedRef.current = true;
      }
      return;
    }

    // Autocomplete accept/dismiss (Tab, Enter, Escape)
    if (acItems.length > 0) {
      if (e.key === 'Tab' || e.key === 'Enter') {
        e.preventDefault();
        acceptSuggestion(acItems[acIndex].text);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setAcItems([]);
        acDismissedRef.current = true;
        return;
      }
    }
  }

  function handleSave() {
    const name = window.prompt('Query name:', 'Untitled query');
    if (name) {
      saveMutation.mutate(name);
    }
  }

  function handleHistorySelect(entry: HistoryEntry) {
    setSql(entry.sql);
    setShowHistory(false);
    setAcItems([]);
    setAcPartial('');
  }

  function handleEditorScroll(e: React.UIEvent<HTMLTextAreaElement>) {
    if (highlightRef.current) {
      highlightRef.current.scrollTop = e.currentTarget.scrollTop;
      highlightRef.current.scrollLeft = e.currentTarget.scrollLeft;
    }
    if (acItems.length > 0) {
      setAcItems([]);
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

      <div className={styles.nlBar}>
        <input
          className={styles.nlInput}
          placeholder="Ask in plain English… e.g. &quot;show me failed logins in the last 24 hours&quot;"
          value={nlInput}
          onChange={(e) => setNlInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleNlSubmit();
          }}
          role="searchbox"
        />
        <Button size="sm" onClick={handleNlSubmit} disabled={nlMutation.isPending}>
          {nlMutation.isPending ? '…' : 'Translate'}
        </Button>
      </div>
      {nlResults.length > 0 && (
        <div className={styles.nlResults}>
          {nlResults.map((interp, i) => (
            <button
              key={i}
              className={styles.nlCard}
              onClick={() => handleNlSelect(interp)}
            >
              <div className={styles.nlCardDesc}>{interp.description}</div>
              <div className={styles.nlCardConf}>
                {Math.round(interp.confidence * 100)}% confidence
              </div>
              <code className={styles.nlCardSql}>{interp.sql}</code>
            </button>
          ))}
        </div>
      )}
      {nlMutation.isError && (
        <ErrorBanner message="Failed to translate query" />
      )}

      <div className={styles.queryLayout}>
        {/* Schema tree */}
        <div className={styles.schemaTree}>
          <div className={styles.schemaTitle}>Schema</div>
          {SCHEMA.map((s) => (
            <div key={s.table}>
              <div className={styles.schemaTable} onClick={() => toggleTable(s.table)}>
                {expandedTables.has(s.table) ? '▼' : '▶'} {s.table}
              </div>
              {expandedTables.has(s.table) &&
                s.cols.map((c) => (
                  <div
                    key={c.name}
                    className={`${styles.schemaCol} ${styles.schemaColClickable}`}
                    onClick={() => insertAtCursor(c.name)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') insertAtCursor(c.name);
                    }}
                  >
                    <span className={styles.schemaType}>{c.type}</span>&nbsp;{c.name}
                  </div>
                ))}
            </div>
          ))}

          {templates && templates.length > 0 && (
            <>
              <div className={styles.schemaTitle} style={{ marginTop: 16 }}>
                Templates
              </div>
              {templates.map((t) => (
                <div
                  key={t.id}
                  className={styles.schemaTable}
                  onClick={() => {
                    setSql(t.sql);
                    setAcItems([]);
                    setAcPartial('');
                  }}
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
              {validationStatus === 'valid' && (
                <span className={styles.validDot} title="Query is valid" />
              )}
              {validationStatus === 'invalid' && (
                <span className={styles.invalidDot} title={validationError} />
              )}
              <div className={styles.toolbarActions}>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => runMutation.mutate(sql)}
                  disabled={runMutation.isPending}
                >
                  {runMutation.isPending ? '…' : '▶ Run'}
                </Button>
                <span className={styles.shortcutHint}>{IS_MAC ? '⌘' : 'Ctrl'}+↵</span>
                <Button size="sm" onClick={handleSave} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? '…' : 'Save'}
                </Button>
                <div className={styles.historyWrap}>
                  <Button size="sm" onClick={() => setShowHistory((v) => !v)}>
                    History
                  </Button>
                  {showHistory && (
                    <>
                      <div
                        className={styles.historyBackdrop}
                        onClick={() => setShowHistory(false)}
                      />
                      <div className={styles.historyDropdown}>
                        {history.length === 0 ? (
                          <div className={styles.historyEmpty}>No queries run yet</div>
                        ) : (
                          history.map((entry, i) => (
                            <div
                              key={i}
                              className={styles.historyItem}
                              onClick={() => handleHistorySelect(entry)}
                            >
                              <div className={styles.historySql}>
                                {entry.sql.slice(0, 80)}
                                {entry.sql.length > 80 ? '…' : ''}
                              </div>
                              <div className={styles.historyTime}>
                                {formatAbsolute(entry.timestamp)}
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
                <pre ref={highlightRef} className={styles.editorHighlight} aria-hidden="true">
                  {renderHighlightedSql(sql, errorRange)}
                </pre>
                <textarea
                  ref={textareaRef}
                  className={styles.editorCode}
                  value={sql}
                  onChange={handleSqlChange}
                  onKeyDown={handleKeyDown}
                  onScroll={handleEditorScroll}
                  spellCheck={false}
                  rows={lines.length}
                />
                {acItems.length > 0 && (
                  <SqlAutocomplete
                    items={acItems}
                    activeIndex={acIndex}
                    position={acPosition}
                    partial={acPartial}
                    onAccept={acceptSuggestion}
                  />
                )}
              </div>
            </div>
          </div>

          {validationStatus === 'invalid' && validationError && (
            <div className={styles.errorBar}>
              <span className={styles.errorBarIcon}>⚠</span>
              <span className={styles.errorBarText}>{validationError}</span>
            </div>
          )}

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
                  onKeyDown={(e) => {
                    if (e.key === 'Enter')
                      resultsTableRef.current?.scrollIntoView({ behavior: 'smooth' });
                  }}
                >
                  {results.row_count} row{results.row_count !== 1 ? 's' : ''}
                </span>
                {' · '}
                <span
                  className={styles.clickableMeta}
                  role="button"
                  tabIndex={0}
                  onClick={() => setShowExecModal(true)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') setShowExecModal(true);
                  }}
                >
                  {results.execution_ms}ms
                </span>
                {results.truncated && (
                  <span style={{ color: 'var(--attention)' }}> (truncated)</span>
                )}
              </div>
              <div className={styles.resultsTable} ref={resultsTableRef}>
                <DataTable<QueryResultRow>
                  columns={queryResultColumns}
                  data={queryResultRows}
                  rowKey={(row) => row.__rowIndex as number}
                  emptyMessage="No results"
                />
              </div>
            </>
          )}
        </div>
      </div>

      {results && (
        <Modal
          open={showExecModal}
          onClose={() => setShowExecModal(false)}
          title="Query Execution Details"
          width={420}
        >
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
            Additional metrics like rows scanned and bytes processed require query engine
            instrumentation.
          </p>
        </Modal>
      )}
    </div>
  );
}
