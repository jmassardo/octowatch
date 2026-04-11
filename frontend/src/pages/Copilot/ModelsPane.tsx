import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getCopilotModels } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

type MetricRow = { metric: string; value: string };

const metricValueColumns: ColumnDef<MetricRow>[] = [
  {
    key: 'metric',
    header: 'Metric',
    filterable: true,
    render: (row) => <span style={{ color: 'var(--fg-muted)' }}>{row.metric}</span>,
    filterValue: (row) => row.metric,
  },
  {
    key: 'value',
    header: 'Value',
    render: (row) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.value}</span>,
  },
];

type ModelsModal = 'model' | 'feature' | 'editor' | null;

export function ModelsPane() {
  const {
    data: models,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['copilot', 'models'],
    queryFn: getCopilotModels,
    staleTime: 300_000,
  });

  const modelUsage = models?.models ?? [];
  const featureUsage = models?.features ?? [];
  const editors = models?.editors ?? [];
  const maxFeatureCount =
    featureUsage.length > 0 ? Math.max(...featureUsage.map((f) => f.count)) : 1;
  const [modelsModal, setModelsModal] = useState<ModelsModal>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const [selectedEditor, setSelectedEditor] = useState<string | null>(null);

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
  const selectedFeatureData = featureUsage.find((f) => f.feature === selectedFeature);
  const selectedEditorData = editors.find((e) => e.name === selectedEditor);

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
          <div className={styles.grid2}>
            {/* Model usage spread */}
            <Card>
              <CardHeader>Model usage spread</CardHeader>
              <div className={styles.langBars}>
                {modelUsage.map((m) => (
                  <div
                    key={m.model}
                    className={`${styles.langRow} ${styles.langRowClickable}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => openModelModal(m.model)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openModelModal(m.model);
                      }
                    }}
                  >
                    <span className={styles.langName} style={{ width: 100 }}>
                      {m.model}
                    </span>
                    <div className={styles.langTrack}>
                      <div
                        style={{
                          width: `${m.pct}%`,
                          height: '100%',
                          background: m.color,
                          borderRadius: 4,
                        }}
                      />
                    </div>
                    <span className={styles.langPct}>{m.pct}%</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* Feature usage spread */}
            <Card>
              <CardHeader>Feature usage spread</CardHeader>
              <div className={styles.langBars}>
                {featureUsage.map((f) => (
                  <div
                    key={f.feature}
                    className={`${styles.langRow} ${styles.langRowClickable}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => openFeatureModal(f.feature)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openFeatureModal(f.feature);
                      }
                    }}
                  >
                    <span className={styles.langName} style={{ width: 120 }}>
                      {f.feature}
                    </span>
                    <div className={styles.langTrack}>
                      <div
                        style={{
                          width: `${(f.count / maxFeatureCount) * 100}%`,
                          height: '100%',
                          background: f.color,
                          borderRadius: 4,
                        }}
                      />
                    </div>
                    <span className={styles.langPct}>{f.count}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Editor breakdown */}
          <div className={styles.sectionTitle}>Editor breakdown</div>
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

          {/* Model detail modal */}
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
                  Per-user and per-team model preference breakdowns require the Copilot Metrics API
                  integration.
                </p>
              </div>
            )}
          </Modal>

          {/* Feature usage detail modal */}
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
                  Use the <strong>Teams</strong> tab for per-team feature usage breakdowns and
                  adoption trends.
                </p>
              </div>
            )}
          </Modal>

          {/* Editor detail modal */}
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
        </>
      )}
    </>
  );
}
