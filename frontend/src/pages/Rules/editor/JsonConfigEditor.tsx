import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import styles from './JsonConfigEditor.module.css';

interface JsonConfigEditorProps {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
  onValidityChange?: (valid: boolean) => void;
  errors?: string[];
  readOnly?: boolean;
}

function countLines(text: string): number {
  if (text === '') return 1;
  let count = 1;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\n') count++;
  }
  return count;
}

function extractErrorPosition(message: string): { line: number; column: number } | null {
  // JSON.parse errors typically include "at position N" or "at line X column Y"
  const posMatch = /position (\d+)/i.exec(message);
  if (posMatch) {
    return { line: -1, column: parseInt(posMatch[1], 10) };
  }
  const lineColMatch = /line (\d+) column (\d+)/i.exec(message);
  if (lineColMatch) {
    return { line: parseInt(lineColMatch[1], 10), column: parseInt(lineColMatch[2], 10) };
  }
  return null;
}

function positionToLineCol(text: string, position: number): { line: number; column: number } {
  let line = 1;
  let col = 1;
  for (let i = 0; i < position && i < text.length; i++) {
    if (text[i] === '\n') {
      line++;
      col = 1;
    } else {
      col++;
    }
  }
  return { line, column: col };
}

export function JsonConfigEditor({
  config,
  onChange,
  onValidityChange,
  errors,
  readOnly = false,
}: JsonConfigEditorProps) {
  const [text, setText] = useState(() => JSON.stringify(config, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);
  const [copyLabel, setCopyLabel] = useState('Copy');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync text when config prop changes externally (e.g. from WYSIWYG edits).
  // Track by serialized JSON to distinguish parent updates from user edits.
  const [lastPropJson, setLastPropJson] = useState(() => JSON.stringify(config));
  const currentPropJson = JSON.stringify(config);
  if (currentPropJson !== lastPropJson) {
    setLastPropJson(currentPropJson);
    setText(JSON.stringify(config, null, 2));
    setParseError(null);
  }

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const newHeight = Math.min(Math.max(ta.scrollHeight, 200), 500);
    ta.style.height = `${newHeight}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [text, adjustHeight]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value;
      setText(value);

      try {
        const parsed: unknown = JSON.parse(value);
        if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
          setParseError(null);
          onChange(parsed as Record<string, unknown>);
          onValidityChange?.(true);
        } else {
          setParseError('Root value must be a JSON object');
          onValidityChange?.(false);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        const pos = extractErrorPosition(msg);
        if (pos) {
          const loc = pos.line === -1 ? positionToLineCol(value, pos.column) : pos;
          setParseError(`${msg} (line ${loc.line}, column ${loc.column})`);
        } else {
          setParseError(msg);
        }
        onValidityChange?.(false);
      }
    },
    [onChange, onValidityChange],
  );

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.currentTarget;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const value = ta.value;

      const newValue = value.substring(0, start) + '  ' + value.substring(end);
      setText(newValue);

      // Restore cursor position after React re-renders
      requestAnimationFrame(() => {
        ta.selectionStart = start + 2;
        ta.selectionEnd = start + 2;
      });
    }
  }, []);

  const handleFormat = useCallback(() => {
    try {
      const parsed: unknown = JSON.parse(text);
      const formatted = JSON.stringify(parsed, null, 2);
      setText(formatted);
      setParseError(null);
      if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
        onChange(parsed as Record<string, unknown>);
        onValidityChange?.(true);
      }
    } catch {
      // Cannot format invalid JSON — error is already shown
    }
  }, [text, onChange, onValidityChange]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyLabel('Copied!');
      setTimeout(() => setCopyLabel('Copy'), 1500);
    } catch {
      // Clipboard API may fail in some contexts; silently ignore
    }
  }, [text]);

  const lineNumbers = useMemo(() => {
    const count = countLines(text);
    const lines: string[] = [];
    for (let i = 1; i <= count; i++) {
      lines.push(String(i));
    }
    return lines.join('\n');
  }, [text]);

  const isValid = parseError === null;

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <div className={isValid ? styles.valid : styles.invalid}>
          <span className={styles.status}>
            <span className={styles.statusDot} />
            {isValid ? 'Valid JSON' : 'Invalid JSON'}
          </span>
        </div>
        {!readOnly && (
          <div className={styles.toolbarActions}>
            <button
              type="button"
              className={styles.toolBtn}
              onClick={handleFormat}
              disabled={!isValid}
            >
              Format
            </button>
            <button type="button" className={styles.toolBtn} onClick={handleCopy}>
              {copyLabel}
            </button>
          </div>
        )}
      </div>

      <div className={`${styles.editorWrap}${parseError ? ` ${styles.hasError}` : ''}`}>
        <div className={styles.gutter} aria-hidden="true">
          {lineNumbers}
        </div>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          readOnly={readOnly}
          data-testid="json-textarea"
        />
      </div>

      {parseError && (
        <div className={styles.errorDetail} data-testid="json-parse-error">
          {parseError}
        </div>
      )}

      {errors && errors.length > 0 && (
        <div className={styles.validationErrors}>
          {errors.map((err, i) => (
            <div key={i} className={styles.validationError}>
              {err}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
