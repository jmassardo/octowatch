import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { DonutChart } from '../../components/charts/DonutChart';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import {
  getCopilotModels,
  getCopilotOverview,
  getCopilotModelUsers,
} from '../../api/copilotMetrics';
import type { CopilotModelUser } from '../../api/copilotMetrics';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

type MetricRow = { metric: string; value: string };

const metricValueColumns: ColumnDef<MetricRow>[] = [
  {
    key: 'metric',
    header: 'Metric',
    filterable: true,
    helpText: 'The name of the model or feature metric. From daily Copilot usage API sync.',
    render: (row) => <span style={{ color: 'var(--fg-muted)' }}>{row.metric}</span>,
    filterValue: (row) => row.metric,
  },
  {
    key: 'value',
    header: 'Value',
    helpText: 'The value of this metric. From daily Copilot usage API sync data.',
    render: (row) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.value}</span>,
  },
];

type ModelsModal = 'model' | 'feature' | 'editor' | 'language' | null;

const MODEL_LINE_COLORS = [
  '#58a6ff',
  '#bc8cff',
  '#3fb950',
  '#db6d28',
  '#79c0ff',
  '#f0883e',
  '#56d364',
  '#d2a8ff',
  '#f85149',
  '#d29922',
];

const FEATURE_LINE_COLORS = ['#3fb950', '#58a6ff', '#bc8cff', '#db6d28', '#79c0ff'];

export function ModelsPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const {
    data: models,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['copilot', 'models', orgParam],
    queryFn: () => getCopilotModels(orgParam),
    staleTime: 30 * 60 * 1000,
  });

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['copilot', 'overview', orgParam],
    queryFn: () => getCopilotOverview(orgParam),
    staleTime: 30 * 60 * 1000,
  });

  const { data: modelUsers } = useQuery({
    queryKey: ['copilot', 'model-users', orgParam],
    queryFn: () => getCopilotModelUsers(orgParam),
    staleTime: 30 * 60 * 1000,
  });

  const modelUsage = models?.models ?? [];
  const featureUsage = models?.features ?? [];
  const editors = models?.editors ?? [];
  const timeSeries = models?.time_series;
  const languages = overview?.languages ?? [];
  const userUsageList = modelUsers?.users ?? [];

  const [modelsModal, setModelsModal] = useState<ModelsModal>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const [selectedEditor, setSelectedEditor] = useState<string | null>(null);
  const [selectedLang, setSelectedLang] = useState<string | null>(null);

  function openModelModal(model: string) {
    setSelectedModel(model);
    setModelsModal('model');
  }

  function openFeatureModal(feature: string) {
    setSelectedFeature(feature);
    setModelsModal('feature');
  }

  function openEditorModal(editor: string) {
    setSelectedEditor(editor);
    setModelsModal('editor');
  }

  const selectedModelData = modelUsage.find((m) => m.model === selectedModel);
  const selectedModelIndex = modelUsage.findIndex((m) => m.model === selectedModel);
  const selectedFeatureData = featureUsage.find((f) => f.feature === selectedFeature);
  const selectedEditorData = editors.find((e) => e.name === selectedEditor);

  function deriveFeatureType(feature: string): string {
    const f = feature.toLowerCase();
    if (f.includes('completion') || f.includes('code')) return 'Code';
    if (f.includes('chat')) return 'Chat';
    if (f.includes('pull_request') || f.includes('pr')) return 'PR Review';
    return 'Other';
  }

  function deriveModelCategory(model: string): string {
    const m = model.toLowerCase();
    if (m.includes('gpt')) return 'OpenAI';
    if (m.includes('claude')) return 'Anthropic';
    return 'Other';
  }

  /** Format date strings for chart x-axis (e.g., "Jun 01") */
  function formatDate(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
  }

  return (
    <>
      {models?.error && (
        <SampleDataBanner
          message={models.message ?? 'Model and feature usage data is unavailable.'}
        />
      )}

      {isError && <ErrorBanner message="Failed to load models data" />}
      {isLoading && <Spinner />}

      {!isLoading && !isError && (
        <>
          {/* ── Donut Charts: Model & Feature Distribution ── */}
          <div className={styles.grid2}>
            <Card>
              <CardHeader>Model usage distribution</CardHeader>
              {modelUsage.length === 0 ? (
                <div
                  style={{
                    color: 'var(--fg-muted)',
                    fontSize: 13,
                    padding: '16px',
                    textAlign: 'center',
                  }}
                >
                  No model usage data — sync Copilot metrics to populate.
                </div>
              ) : (
                <DonutChart
                  data={modelUsage.map((m) => ({
                    name: m.model,
                    value: m.pct,
                    color: m.color,
                  }))}
                  height={260}
                  onItemClick={openModelModal}
                />
              )}
            </Card>

            <Card>
              <CardHeader>Feature usage distribution</CardHeader>
              {featureUsage.length === 0 ? (
                <div
                  style={{
                    color: 'var(--fg-muted)',
                    fontSize: 13,
                    padding: '16px',
                    textAlign: 'center',
                  }}
                >
                  No feature usage data — sync Copilot metrics to populate.
                </div>
              ) : (
                <DonutChart
                  data={featureUsage.map((f) => ({
                    name: f.feature,
                    value: f.count,
                    color: f.color,
                  }))}
                  height={260}
                  onItemClick={openFeatureModal}
                />
              )}
            </Card>
          </div>

          {/* ── Time Series: Model Trends ── */}
          {timeSeries && Object.keys(timeSeries.models).length > 0 && (
            <Card style={{ marginTop: 20 }}>
              <CardHeader>Model usage trends (last 28 days)</CardHeader>
              <div style={{ padding: '8px 16px 16px' }}>
                <LineAreaChart
                  xAxisData={timeSeries.dates.map(formatDate)}
                  series={Object.entries(timeSeries.models).map(([name, data], i) => ({
                    name,
                    data,
                    color: MODEL_LINE_COLORS[i % MODEL_LINE_COLORS.length],
                    areaOpacity: 0.08,
                  }))}
                  height={220}
                  yAxisFormatter={(v) => String(Math.round(v))}
                />
              </div>
            </Card>
          )}

          {/* ── Time Series: Feature Trends ── */}
          {timeSeries && Object.keys(timeSeries.features).length > 0 && (
            <Card style={{ marginTop: 20 }}>
              <CardHeader>Feature usage trends (last 28 days)</CardHeader>
              <div style={{ padding: '8px 16px 16px' }}>
                <LineAreaChart
                  xAxisData={timeSeries.dates.map(formatDate)}
                  series={Object.entries(timeSeries.features).map(([name, data], i) => ({
                    name,
                    data,
                    color: FEATURE_LINE_COLORS[i % FEATURE_LINE_COLORS.length],
                    areaOpacity: 0.12,
                  }))}
                  height={220}
                  yAxisFormatter={(v) => String(Math.round(v))}
                />
              </div>
            </Card>
          )}

          {/* ── Acceptance Rate by Language (moved from Overview) ── */}
          <Card style={{ marginTop: 20 }}>
            <CardHeader>Acceptance rate by language</CardHeader>
            {overviewLoading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
                <Spinner />
              </div>
            ) : languages.length > 0 ? (
              <div className={styles.langBars}>
                {languages.map((l) => (
                  <div
                    key={l.lang}
                    className={`${styles.langRow} ${styles.langRowClickable}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      setSelectedLang(l.lang);
                      setModelsModal('language');
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setSelectedLang(l.lang);
                        setModelsModal('language');
                      }
                    }}
                  >
                    <span className={styles.langName}>{l.lang}</span>
                    <div className={styles.langTrack}>
                      <div
                        style={{
                          width: `${l.pct}%`,
                          height: '100%',
                          background: l.color,
                          borderRadius: 4,
                        }}
                      />
                    </div>
                    <span className={styles.langPct}>{l.pct}%</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: 'var(--fg-muted)', padding: '12px 0' }}>
                No language data available.
              </div>
            )}
            <div className={styles.langNote}>
              Language data from Copilot telemetry (not available via audit log)
            </div>
          </Card>

          {/* ── Editor Breakdown ── */}
          <div className={styles.sectionTitle} style={{ marginTop: 24 }}>
            Editor breakdown
          </div>
          {editors.length === 0 ? (
            <div
              style={{
                color: 'var(--fg-muted)',
                fontSize: 13,
                padding: '16px 0',
                textAlign: 'center',
              }}
            >
              No editor usage data — sync Copilot metrics to populate.
            </div>
          ) : (
            <div className={styles.editorGrid}>
              {editors.map((e) => (
                <div
                  key={e.name}
                  className={styles.editorCardClickable}
                  role="button"
                  tabIndex={0}
                  onClick={() => openEditorModal(e.name)}
                  onKeyDown={(ev) => {
                    if (ev.key === 'Enter' || ev.key === ' ') {
                      ev.preventDefault();
                      openEditorModal(e.name);
                    }
                  }}
                >
                  <Card className={styles.editorCard}>
                    <div className={styles.editorCount}>{e.count}</div>
                    <div className={styles.editorName}>{e.name}</div>
                    <div className={styles.editorPct}>{e.pct}%</div>
                  </Card>
                </div>
              ))}
            </div>
          )}

          {/* ── Per-User Copilot Usage Table ── */}
          <Card style={{ marginTop: 24 }}>
            <CardHeader>Per-user Copilot usage (last 28 days)</CardHeader>
            {userUsageList.length === 0 ? (
              <div
                style={{
                  color: 'var(--fg-muted)',
                  fontSize: 13,
                  padding: '16px',
                  textAlign: 'center',
                }}
              >
                No per-user usage data available — sync Copilot usage reports to populate.
              </div>
            ) : (
              <DataTable<CopilotModelUser>
                columns={[
                  {
                    key: 'login',
                    header: 'User',
                    filterable: true,
                    sortable: true,
                    render: (u) => (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <img
                          src={`https://github.com/${u.login}.png?size=24`}
                          alt={u.login}
                          style={{ width: 20, height: 20, borderRadius: '50%' }}
                        />
                        <span style={{ fontWeight: 500 }}>{u.login}</span>
                      </span>
                    ),
                    filterValue: (u) => u.login,
                    sortValue: (u) => u.login,
                  },
                  {
                    key: 'total_credits',
                    header: 'Total Credits',
                    sortable: true,
                    render: (u) => (
                      <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                        {u.total_credits.toFixed(1)}
                      </span>
                    ),
                    sortValue: (u) => u.total_credits,
                  },
                  {
                    key: 'completions_credits',
                    header: 'Completions',
                    sortable: true,
                    render: (u) => (
                      <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {u.completions_credits.toFixed(1)}
                      </span>
                    ),
                    sortValue: (u) => u.completions_credits,
                  },
                  {
                    key: 'chat_credits',
                    header: 'Chat',
                    sortable: true,
                    render: (u) => (
                      <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {u.chat_credits.toFixed(1)}
                      </span>
                    ),
                    sortValue: (u) => u.chat_credits,
                  },
                  {
                    key: 'pr_credits',
                    header: 'PR Review',
                    sortable: true,
                    render: (u) => (
                      <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {u.pr_credits.toFixed(1)}
                      </span>
                    ),
                    sortValue: (u) => u.pr_credits,
                  },
                  {
                    key: 'days_active',
                    header: 'Days Active',
                    sortable: true,
                    render: (u) => (
                      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{u.days_active}d</span>
                    ),
                    sortValue: (u) => u.days_active,
                  },
                  {
                    key: 'last_active',
                    header: 'Last Active',
                    sortable: true,
                    render: (u) => (
                      <span style={{ color: 'var(--fg-muted)', fontSize: 12 }}>
                        {u.last_active ?? '—'}
                      </span>
                    ),
                    sortValue: (u) => u.last_active ?? '',
                  },
                ]}
                data={userUsageList}
                rowKey={(u) => u.login}
                pageSize={15}
              />
            )}
          </Card>

          {/* ── Model Detail Modal ── */}
          <Modal
            open={modelsModal === 'model'}
            onClose={() => setModelsModal(null)}
            title={
              selectedModelData ? `${selectedModelData.model} — usage details` : 'Model details'
            }
            width={520}
          >
            {selectedModelData && (
              <div>
                <DataTable<MetricRow>
                  columns={metricValueColumns}
                  data={[
                    { metric: 'Model', value: selectedModelData.model },
                    { metric: 'Usage share', value: `${selectedModelData.pct}%` },
                    {
                      metric: 'Ranking',
                      value: `#${selectedModelIndex + 1} most used model`,
                    },
                    {
                      metric: 'Category',
                      value: deriveModelCategory(selectedModelData.model),
                    },
                  ]}
                  rowKey={(row) => row.metric}
                  className={styles.modalTable}
                />
              </div>
            )}
          </Modal>

          {/* ── Feature Usage Detail Modal ── */}
          <Modal
            open={modelsModal === 'feature'}
            onClose={() => setModelsModal(null)}
            title={
              selectedFeatureData
                ? `${selectedFeatureData.feature} — usage details`
                : 'Feature details'
            }
            width={520}
          >
            {selectedFeatureData && (
              <div>
                <DataTable<MetricRow>
                  columns={metricValueColumns}
                  data={[
                    { metric: 'Feature', value: selectedFeatureData.feature },
                    { metric: 'Active users', value: String(selectedFeatureData.count) },
                    {
                      metric: 'Feature type',
                      value: deriveFeatureType(selectedFeatureData.feature),
                    },
                  ]}
                  rowKey={(row) => row.metric}
                  className={styles.modalTable}
                />
              </div>
            )}
          </Modal>

          {/* ── Editor Detail Modal ── */}
          <Modal
            open={modelsModal === 'editor'}
            onClose={() => setModelsModal(null)}
            title={
              selectedEditorData ? `${selectedEditorData.name} — editor details` : 'Editor details'
            }
            width={520}
          >
            {selectedEditorData && (
              <div>
                <DataTable<MetricRow>
                  columns={metricValueColumns}
                  data={[
                    { metric: 'Editor', value: selectedEditorData.name },
                    { metric: 'Active users', value: String(selectedEditorData.count) },
                    { metric: 'Share', value: `${selectedEditorData.pct}%` },
                  ]}
                  rowKey={(row) => row.metric}
                  className={styles.modalTable}
                />
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--fg-muted)',
                    lineHeight: 1.6,
                    margin: '12px 0 0',
                  }}
                >
                  User distribution by editor and team-level editor preferences require the Copilot
                  Metrics API integration.
                </p>
              </div>
            )}
          </Modal>

          {/* ── Language Drill-Down Modal ── */}
          <Modal
            open={modelsModal === 'language'}
            onClose={() => setModelsModal(null)}
            title={selectedLang ? `${selectedLang} — Acceptance rate details` : 'Language details'}
            width={520}
          >
            {selectedLang &&
              (() => {
                const lang = languages.find((l) => l.lang === selectedLang);
                return lang ? (
                  <div>
                    <p
                      style={{
                        fontSize: 13,
                        color: 'var(--fg-muted)',
                        lineHeight: 1.6,
                        margin: '0 0 12px',
                      }}
                    >
                      <strong>{lang.lang}</strong> has an acceptance rate of{' '}
                      <strong>{lang.pct}%</strong>.
                    </p>
                    <p
                      style={{
                        fontSize: 13,
                        color: 'var(--fg-muted)',
                        lineHeight: 1.6,
                        margin: 0,
                      }}
                    >
                      Per-language acceptance breakdowns by team and user require the Copilot
                      Metrics API. This would show which teams are most effective with {lang.lang}{' '}
                      completions and where additional training may help.
                    </p>
                  </div>
                ) : null;
              })()}
          </Modal>
        </>
      )}
    </>
  );
}
