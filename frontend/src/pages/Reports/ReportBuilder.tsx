import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createCustomReport } from '../../api/reports';
import { useToast } from '../../hooks/useToast';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { Card, CardHeader } from '../../components/primitives/Card';
import type {
  DataSourceType,
  VisualizationType,
  CustomReportColumnDef,
  CustomReportFilterDef,
  CustomReportGrouping,
  CustomReportCreate,
} from '../../types/reports';
import styles from './Reports.module.css';

const DATA_SOURCES: { id: DataSourceType; label: string; description: string }[] = [
  { id: 'events', label: 'Events', description: 'Audit log events' },
  { id: 'detections', label: 'Detections', description: 'Security detections' },
  { id: 'posture', label: 'Security Posture', description: 'Code scanning alerts' },
  { id: 'copilot', label: 'Copilot', description: 'Copilot usage events' },
  { id: 'workflows', label: 'Workflows', description: 'Workflow scan activities' },
  { id: 'users', label: 'Users', description: 'User activity events' },
];

const FIELDS_BY_SOURCE: Record<DataSourceType, { field: string; label: string }[]> = {
  events: [
    { field: 'action', label: 'Action' },
    { field: 'actor', label: 'Actor' },
    { field: 'actor_id', label: 'Actor ID' },
    { field: 'org', label: 'Organization' },
    { field: 'repo', label: 'Repository' },
    { field: 'created_at', label: 'Timestamp' },
    { field: 'country', label: 'Country' },
    { field: 'actor_ip', label: 'IP Address' },
  ],
  detections: [
    { field: 'title', label: 'Title' },
    { field: 'severity', label: 'Severity' },
    { field: 'status', label: 'Status' },
    { field: 'actor', label: 'Actor' },
    { field: 'org', label: 'Organization' },
    { field: 'repo', label: 'Repository' },
    { field: 'created_at', label: 'Timestamp' },
    { field: 'rule_id', label: 'Rule ID' },
  ],
  posture: [
    { field: 'rule_id', label: 'Rule ID' },
    { field: 'severity', label: 'Severity' },
    { field: 'state', label: 'State' },
    { field: 'tool_name', label: 'Tool' },
    { field: 'created_at', label: 'Timestamp' },
  ],
  copilot: [
    { field: 'action', label: 'Action' },
    { field: 'actor', label: 'Actor' },
    { field: 'org', label: 'Organization' },
    { field: 'created_at', label: 'Timestamp' },
  ],
  workflows: [
    { field: 'org', label: 'Organization' },
    { field: 'repo', label: 'Repository' },
    { field: 'workflow_path', label: 'Workflow Path' },
    { field: 'status', label: 'Status' },
    { field: 'started_at', label: 'Started At' },
    { field: 'findings_count', label: 'Findings Count' },
  ],
  users: [
    { field: 'actor', label: 'Actor' },
    { field: 'org', label: 'Organization' },
    { field: 'action', label: 'Action' },
    { field: 'created_at', label: 'Timestamp' },
  ],
};

const GROUPING_OPTIONS = [
  { value: 'org', label: 'Organization' },
  { value: 'repo', label: 'Repository' },
  { value: 'actor', label: 'Actor' },
  { value: 'action', label: 'Action' },
  { value: 'severity', label: 'Severity' },
];

const TIME_BUCKET_OPTIONS = [
  { value: '', label: 'No time bucketing' },
  { value: 'hourly', label: 'Hourly' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
];

const VISUALIZATION_OPTIONS: { value: VisualizationType; label: string }[] = [
  { value: 'table', label: 'Table only' },
  { value: 'table_chart', label: 'Table + Chart' },
  { value: 'chart', label: 'Chart only' },
];

const FILTER_OPERATORS = [
  { value: 'eq', label: 'Equals' },
  { value: 'neq', label: 'Not equals' },
  { value: 'gt', label: 'Greater than' },
  { value: 'gte', label: 'Greater or equal' },
  { value: 'lt', label: 'Less than' },
  { value: 'lte', label: 'Less or equal' },
  { value: 'contains', label: 'Contains' },
];

interface ReportBuilderProps {
  onClose: () => void;
  onCreated: () => void;
}

export function ReportBuilder({ onClose, onCreated }: ReportBuilderProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);

  // Step 1: Data sources
  const [selectedSources, setSelectedSources] = useState<DataSourceType[]>([]);

  // Step 2: Columns
  const [selectedColumns, setSelectedColumns] = useState<CustomReportColumnDef[]>([]);

  // Step 3: Filters
  const [filters, setFilters] = useState<CustomReportFilterDef[]>([]);
  const [newFilterField, setNewFilterField] = useState('');
  const [newFilterOperator, setNewFilterOperator] =
    useState<CustomReportFilterDef['operator']>('eq');
  const [newFilterValue, setNewFilterValue] = useState('');

  // Step 4: Grouping
  const [groupBy, setGroupBy] = useState('');
  const [timeBucket, setTimeBucket] = useState('');

  // Step 5: Visualization
  const [visualization, setVisualization] = useState<VisualizationType>('table');

  // Step 6: Name and save
  const [reportName, setReportName] = useState('');
  const [reportDescription, setReportDescription] = useState('');

  const availableFields =
    selectedSources.length > 0 ? (FIELDS_BY_SOURCE[selectedSources[0]] ?? []) : [];

  const toggleSource = useCallback((source: DataSourceType) => {
    setSelectedSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source],
    );
    // Reset columns when sources change
    setSelectedColumns([]);
  }, []);

  const toggleColumn = useCallback((field: string, label: string) => {
    setSelectedColumns((prev) => {
      const exists = prev.find((c) => c.field === field);
      if (exists) return prev.filter((c) => c.field !== field);
      return [...prev, { field, label, visible: true }];
    });
  }, []);

  const addFilter = useCallback(() => {
    if (!newFilterField || !newFilterValue) return;
    setFilters((prev) => [
      ...prev,
      { field: newFilterField, operator: newFilterOperator, value: newFilterValue },
    ]);
    setNewFilterField('');
    setNewFilterValue('');
    setNewFilterOperator('eq');
  }, [newFilterField, newFilterOperator, newFilterValue]);

  const removeFilter = useCallback((index: number) => {
    setFilters((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const createMutation = useMutation({
    mutationFn: (body: CustomReportCreate) => createCustomReport(body),
    onSuccess: () => {
      showToast('Custom report created successfully', 'success');
      void queryClient.invalidateQueries({ queryKey: ['custom-reports'] });
      onCreated();
    },
    onError: () => {
      showToast('Failed to create custom report', 'error');
    },
  });

  const handleSave = useCallback(() => {
    if (!reportName.trim()) {
      showToast('Please enter a report name', 'error');
      return;
    }
    if (selectedSources.length === 0) {
      showToast('Please select at least one data source', 'error');
      return;
    }

    const grouping: CustomReportGrouping = {
      group_by: groupBy || null,
      time_bucket: (timeBucket as CustomReportGrouping['time_bucket']) || null,
    };

    createMutation.mutate({
      name: reportName.trim(),
      description: reportDescription.trim() || undefined,
      data_sources: selectedSources,
      columns: selectedColumns,
      filters,
      grouping,
      visualization,
    });
  }, [
    reportName,
    reportDescription,
    selectedSources,
    selectedColumns,
    filters,
    groupBy,
    timeBucket,
    visualization,
    createMutation,
    showToast,
  ]);

  const canProceed = (): boolean => {
    switch (step) {
      case 1:
        return selectedSources.length > 0;
      case 6:
        return reportName.trim().length > 0;
      default:
        return true;
    }
  };

  const totalSteps = 6;

  return (
    <div className={styles.builderContainer} data-testid="report-builder">
      <div className={styles.configHeader}>
        <h3 className={styles.configTitle}>Custom Report Builder</h3>
        <Button size="sm" onClick={onClose}>
          ✕
        </Button>
      </div>

      {/* Step indicator */}
      <div className={styles.stepIndicator}>
        {Array.from({ length: totalSteps }, (_, i) => i + 1).map((s) => (
          <div
            key={s}
            className={`${styles.stepDot} ${s === step ? styles.stepDotActive : ''} ${s < step ? styles.stepDotCompleted : ''}`}
          >
            {s}
          </div>
        ))}
      </div>

      {/* Step 1: Data sources */}
      {step === 1 && (
        <Card>
          <CardHeader>Step 1: Choose Data Sources</CardHeader>
          <div className={styles.builderGrid}>
            {DATA_SOURCES.map((source) => (
              <div
                key={source.id}
                role="checkbox"
                aria-checked={selectedSources.includes(source.id)}
                tabIndex={0}
                className={`${styles.sourceCard} ${selectedSources.includes(source.id) ? styles.sourceCardSelected : ''}`}
                onClick={() => toggleSource(source.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleSource(source.id);
                  }
                }}
              >
                <div className={styles.sourceLabel}>{source.label}</div>
                <div className={styles.sourceDescription}>{source.description}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Step 2: Columns */}
      {step === 2 && (
        <Card>
          <CardHeader>Step 2: Select Columns</CardHeader>
          <div className={styles.columnList}>
            {availableFields.map((f) => (
              <label key={f.field} className={styles.columnCheckbox}>
                <input
                  type="checkbox"
                  checked={selectedColumns.some((c) => c.field === f.field)}
                  onChange={() => toggleColumn(f.field, f.label)}
                />
                <span>{f.label}</span>
                <span className={styles.fieldName}>({f.field})</span>
              </label>
            ))}
            {availableFields.length === 0 && (
              <p className={styles.emptyReports}>
                Select a data source in Step 1 to see available columns.
              </p>
            )}
          </div>
        </Card>
      )}

      {/* Step 3: Filters */}
      {step === 3 && (
        <Card>
          <CardHeader>Step 3: Add Filters</CardHeader>
          <div className={styles.filterSection}>
            {filters.map((f, idx) => (
              <div key={idx} className={styles.filterRow}>
                <span className={styles.filterLabel}>
                  {f.field} {f.operator} {String(f.value)}
                </span>
                <Button size="sm" onClick={() => removeFilter(idx)}>
                  Remove
                </Button>
              </div>
            ))}
            <div className={styles.filterInputRow}>
              <select
                className={styles.selectInput}
                value={newFilterField}
                onChange={(e) => setNewFilterField(e.target.value)}
                aria-label="Filter field"
              >
                <option value="">Select field…</option>
                {availableFields.map((f) => (
                  <option key={f.field} value={f.field}>
                    {f.label}
                  </option>
                ))}
              </select>
              <select
                className={styles.selectInput}
                value={newFilterOperator}
                onChange={(e) =>
                  setNewFilterOperator(e.target.value as CustomReportFilterDef['operator'])
                }
                aria-label="Filter operator"
              >
                {FILTER_OPERATORS.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                className={styles.textInput}
                placeholder="Value"
                value={newFilterValue}
                onChange={(e) => setNewFilterValue(e.target.value)}
                aria-label="Filter value"
              />
              <Button size="sm" onClick={addFilter}>
                Add
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Step 4: Grouping */}
      {step === 4 && (
        <Card>
          <CardHeader>Step 4: Choose Grouping</CardHeader>
          <div className={styles.configSection}>
            <label className={styles.configLabel}>Group by</label>
            <select
              className={styles.selectInput}
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value)}
              aria-label="Group by field"
            >
              <option value="">No grouping</option>
              {GROUPING_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.configSection}>
            <label className={styles.configLabel}>Time bucket</label>
            <select
              className={styles.selectInput}
              value={timeBucket}
              onChange={(e) => setTimeBucket(e.target.value)}
              aria-label="Time bucket"
            >
              {TIME_BUCKET_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </Card>
      )}

      {/* Step 5: Visualization */}
      {step === 5 && (
        <Card>
          <CardHeader>Step 5: Choose Visualization</CardHeader>
          <div className={styles.vizOptions}>
            {VISUALIZATION_OPTIONS.map((opt) => (
              <label key={opt.value} className={styles.vizOption}>
                <input
                  type="radio"
                  name="visualization"
                  value={opt.value}
                  checked={visualization === opt.value}
                  onChange={() => setVisualization(opt.value)}
                />
                <span>{opt.label}</span>
              </label>
            ))}
          </div>
        </Card>
      )}

      {/* Step 6: Name and save */}
      {step === 6 && (
        <Card>
          <CardHeader>Step 6: Name and Save</CardHeader>
          <div className={styles.configSection}>
            <label className={styles.configLabel}>Report Name</label>
            <input
              type="text"
              className={styles.textInput}
              placeholder="My custom report"
              value={reportName}
              onChange={(e) => setReportName(e.target.value)}
              aria-label="Report name"
              maxLength={255}
            />
          </div>
          <div className={styles.configSection}>
            <label className={styles.configLabel}>Description (optional)</label>
            <textarea
              className={styles.textareaInput}
              placeholder="Describe what this report tracks…"
              value={reportDescription}
              onChange={(e) => setReportDescription(e.target.value)}
              aria-label="Report description"
              maxLength={2000}
              rows={3}
            />
          </div>
          <div className={styles.configSection}>
            <h4 className={styles.summarySectionTitle}>Summary</h4>
            <ul className={styles.summaryList}>
              <li>
                <strong>Sources:</strong> {selectedSources.join(', ') || 'None'}
              </li>
              <li>
                <strong>Columns:</strong>{' '}
                {selectedColumns.map((c) => c.label).join(', ') || 'Default'}
              </li>
              <li>
                <strong>Filters:</strong> {filters.length} filter(s)
              </li>
              <li>
                <strong>Group by:</strong> {groupBy || 'None'}
              </li>
              <li>
                <strong>Visualization:</strong> {visualization}
              </li>
            </ul>
          </div>
        </Card>
      )}

      {/* Navigation buttons */}
      <div className={styles.builderNav}>
        {step > 1 && (
          <Button size="sm" onClick={() => setStep((s) => s - 1)}>
            ← Previous
          </Button>
        )}
        <div className={styles.builderNavRight}>
          {step < totalSteps && (
            <Button size="sm" onClick={() => setStep((s) => s + 1)} disabled={!canProceed()}>
              Next →
            </Button>
          )}
          {step === totalSteps && (
            <Button onClick={handleSave} disabled={!canProceed() || createMutation.isPending}>
              {createMutation.isPending ? (
                <>
                  <Spinner /> Saving…
                </>
              ) : (
                'Save Report'
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
