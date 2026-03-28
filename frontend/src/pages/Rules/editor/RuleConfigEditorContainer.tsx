import { useState, useCallback, useRef, useEffect } from 'react';
import { LogicConfigEditor } from './LogicConfigEditor';
import type { LogicConfig } from './types';
import { JsonConfigEditor } from './JsonConfigEditor';
import { validateRuleConfig } from '../../../api/rules';
import styles from './RuleConfigEditorContainer.module.css';

type EditorMode = 'visual' | 'json';

interface RuleConfigEditorContainerProps {
  logicType: 'pattern' | 'threshold' | 'sequence' | 'statistical';
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}

export function RuleConfigEditorContainer({
  logicType,
  config,
  onChange,
}: RuleConfigEditorContainerProps) {
  const [mode, setMode] = useState<EditorMode>('visual');
  const [jsonValid, setJsonValid] = useState(true);
  const [switchWarning, setSwitchWarning] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  // Debounce timer ref for validation
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleVisualChange = useCallback(
    (newConfig: LogicConfig) => {
      // LogicConfig is a structured subset; spread into Record<string, unknown>
      onChange({ ...newConfig });
    },
    [onChange],
  );

  const handleJsonEditorChange = useCallback(
    (newConfig: Record<string, unknown>) => {
      setSwitchWarning(false);
      onChange(newConfig);
    },
    [onChange],
  );

  const handleJsonValidityChange = useCallback((valid: boolean) => {
    setJsonValid(valid);
    if (valid) {
      setSwitchWarning(false);
    }
  }, []);

  const handleModeSwitch = useCallback(
    (newMode: EditorMode) => {
      if (newMode === mode) return;

      if (newMode === 'visual' && !jsonValid) {
        setSwitchWarning(true);
        return;
      }

      setSwitchWarning(false);
      // Reset validity when switching to JSON mode
      if (newMode === 'json') {
        setJsonValid(true);
      }
      setMode(newMode);
    },
    [mode, jsonValid],
  );

  // Debounced validation on config changes
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      validateRuleConfig(logicType, config)
        .then((result) => {
          setValidationErrors(result.errors);
        })
        .catch(() => {
          // Validation endpoint unavailable; don't block the user
          setValidationErrors([]);
        });
    }, 500);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [logicType, config]);

  return (
    <div className={styles.container}>
      <div className={styles.modeToggle}>
        <button
          type="button"
          className={`${styles.modeTab}${mode === 'visual' ? ` ${styles.active}` : ''}`}
          onClick={() => handleModeSwitch('visual')}
          data-testid="mode-visual"
        >
          Visual
        </button>
        <button
          type="button"
          className={`${styles.modeTab}${mode === 'json' ? ` ${styles.active}` : ''}`}
          onClick={() => handleModeSwitch('json')}
          data-testid="mode-json"
        >
          JSON
        </button>
      </div>

      {switchWarning && (
        <div className={styles.switchWarning} data-testid="switch-warning">
          Fix JSON errors before switching to Visual mode
        </div>
      )}

      <div className={styles.editorBody}>
        {mode === 'visual' ? (
          <LogicConfigEditor
            logicType={logicType}
            config={config as LogicConfig}
            onChange={handleVisualChange}
            errors={validationErrors}
          />
        ) : (
          <JsonConfigEditor
            config={config}
            onChange={handleJsonEditorChange}
            onValidityChange={handleJsonValidityChange}
            errors={validationErrors}
          />
        )}
      </div>
    </div>
  );
}
