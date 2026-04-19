import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Modal } from '../../components/primitives/Modal';
import type { RuleCreate, RuleResponse } from '../../types/detections';
import styles from './RuleLibrary.module.css';

// ─── Types ───────────────────────────────────────────────────────────────────

interface LibraryRule {
  readonly name: string;
  readonly slug: string;
  readonly description: string;
  readonly category: string;
  readonly default_severity: string;
  readonly default_confidence: string;
  readonly logic_type: string;
  readonly logic_config: Record<string, unknown>;
}

interface LibraryCategory {
  readonly category: string;
  readonly display_name: string;
  readonly rules: readonly LibraryRule[];
}

interface LibraryResponse {
  readonly categories: readonly LibraryCategory[];
  readonly total_rules: number;
}

interface CustomizeResponse {
  readonly rule: RuleCreate;
}

// ─── API calls ───────────────────────────────────────────────────────────────

function fetchLibrary(): Promise<LibraryResponse> {
  return api.get<LibraryResponse>('/rules/library');
}

function enableLibraryRule(slug: string): Promise<RuleResponse> {
  return api.post<RuleResponse>(`/rules/library/${slug}/enable`, {});
}

function fetchCustomize(slug: string): Promise<CustomizeResponse> {
  return api.get<CustomizeResponse>(`/rules/library/${slug}/customize`);
}

// ─── Severity badge helper ───────────────────────────────────────────────────

const SEVERITY_VARIANT: Record<string, 'danger' | 'attention' | 'success' | 'muted'> = {
  critical: 'danger',
  high: 'attention',
  medium: 'success',
  low: 'muted',
  info: 'muted',
};

// ─── Component ───────────────────────────────────────────────────────────────

export function RuleLibrary({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [enabledSlugs, setEnabledSlugs] = useState<Set<string>>(new Set());
  const [customizeRule, setCustomizeRule] = useState<LibraryRule | null>(null);
  const [customizeData, setCustomizeData] = useState<RuleCreate | null>(null);

  const {
    data: library,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['rule-library'],
    queryFn: fetchLibrary,
  });

  const enableMutation = useMutation({
    mutationFn: enableLibraryRule,
    onSuccess: (_data, slug) => {
      setEnabledSlugs((prev) => new Set([...prev, slug]));
      qc.invalidateQueries({ queryKey: ['rules'] });
    },
  });

  const customizeMutation = useMutation({
    mutationFn: fetchCustomize,
    onSuccess: (data) => {
      setCustomizeData(data.rule);
    },
  });

  function handleToggleCategory(category: string) {
    setExpandedCategory((prev) => (prev === category ? null : category));
  }

  function handleEnable(slug: string) {
    enableMutation.mutate(slug);
  }

  function handleCustomize(rule: LibraryRule) {
    setCustomizeRule(rule);
    customizeMutation.mutate(rule.slug);
  }

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load rule library" onRetry={() => refetch()} />;
  if (!library) return null;

  return (
    <div className={styles.library}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>Rule Library</h2>
          <p className={styles.subtitle}>
            {library.total_rules} pre-built detection rules across {library.categories.length}{' '}
            categories
          </p>
        </div>
        <Button variant="default" size="sm" onClick={onClose}>
          ← Back to rules
        </Button>
      </div>

      <div className={styles.categories}>
        {library.categories.map((cat) => (
          <div key={cat.category} className={styles.category}>
            <button
              className={styles.categoryHeader}
              onClick={() => handleToggleCategory(cat.category)}
              aria-expanded={expandedCategory === cat.category}
              type="button"
            >
              <span className={styles.categoryChevron}>
                {expandedCategory === cat.category ? '▾' : '▸'}
              </span>
              <span className={styles.categoryName}>{cat.display_name}</span>
              <span className={styles.categoryCount}>{cat.rules.length} rules</span>
            </button>

            {expandedCategory === cat.category && (
              <div className={styles.ruleList}>
                {cat.rules.map((rule) => {
                  const isEnabled = enabledSlugs.has(rule.slug);
                  const isEnabling =
                    enableMutation.isPending && enableMutation.variables === rule.slug;
                  const enableError =
                    enableMutation.isError && enableMutation.variables === rule.slug;

                  return (
                    <div key={rule.slug} className={styles.ruleCard}>
                      <div className={styles.ruleInfo}>
                        <div className={styles.ruleNameRow}>
                          <span className={styles.ruleName}>{rule.name}</span>
                          <Label variant={SEVERITY_VARIANT[rule.default_severity] ?? 'muted'}>
                            {rule.default_severity}
                          </Label>
                          <Label variant="muted">{rule.logic_type}</Label>
                        </div>
                        <p className={styles.ruleDescription}>{rule.description}</p>
                        {enableError && (
                          <span className={styles.enableError}>
                            Rule may already exist. Try customizing instead.
                          </span>
                        )}
                      </div>
                      <div className={styles.ruleActions}>
                        {isEnabled ? (
                          <Label variant="success">Enabled ✓</Label>
                        ) : (
                          <>
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleEnable(rule.slug)}
                              disabled={isEnabling}
                            >
                              {isEnabling ? 'Enabling…' : 'Enable'}
                            </Button>
                            <Button
                              variant="default"
                              size="sm"
                              onClick={() => handleCustomize(rule)}
                            >
                              Customize
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Customize modal */}
      <Modal
        open={!!customizeRule}
        onClose={() => {
          setCustomizeRule(null);
          setCustomizeData(null);
        }}
        title={`Customize: ${customizeRule?.name ?? ''}`}
        width={600}
      >
        {customizeMutation.isPending && <Spinner />}
        {customizeData && (
          <div className={styles.customizeContent}>
            <p className={styles.customizeHint}>
              Copy this configuration and use &ldquo;New rule&rdquo; to create a customized version.
            </p>
            <pre className={styles.customizeJson}>{JSON.stringify(customizeData, null, 2)}</pre>
            <div className={styles.customizeActions}>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(JSON.stringify(customizeData, null, 2));
                  setCustomizeRule(null);
                  setCustomizeData(null);
                }}
              >
                Copy to clipboard
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
