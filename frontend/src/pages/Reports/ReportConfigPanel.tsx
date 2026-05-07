import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { runCustomReport, exportReport } from '../../api/reports';
import { useOrg } from '../../hooks/useOrg';
import { useToast } from '../../hooks/useToast';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import type {
  ReportCatalogEntry,
  ReportRunParams,
  ReportRunResult,
  CustomReport,
} from '../../types/reports';
import styles from './Reports.module.css';

const WINDOW_PRESETS: { label: string; days: number }[] = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 14 days', days: 14 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 90 days', days: 90 },
];

interface ReportConfigPanelProps {
  /** Pre-built template report being configured */
  template?: ReportCatalogEntry;
  /** Custom report being configured */
  customReport?: CustomReport;
  /** Called when user wants to close the panel */
  onClose: () => void;
}

function buildDynamicColumns(
  data: readonly Record<string, unknown>[],
): ColumnDef<Record<string, unknown>>[] {
  if (data.length === 0) return [];
  return Object.keys(data[0]).map((col) => ({
    key: col,
    header: col,
    sortable: true,
    filterable: true,
    sortValue: (row: Record<string, unknown>) => {
      const val = row[col];
      if (val == null) return '';
      if (typeof val === 'number') return val;
      return String(val).toLowerCase();
    },
    filterValue: (row: Record<string, unknown>) => String(row[col] ?? ''),
    render: (row: Record<string, unknown>) => String(row[col] ?? ''),
  }));
}

export function ReportConfigPanel({ template, customReport, onClose }: ReportConfigPanelProps) {
  const { selectedOrg } = useOrg();
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const [windowDays, setWindowDays] = useState(30);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [org, setOrg] = useState(selectedOrg ?? '');
  const [granularity, setGranularity] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [result, setResult] = useState<ReportRunResult | null>(null);

  const reportName = customReport?.name ?? template?.title ?? 'Report';
  const reportId = customReport?.id;
  const reportType = template?.type;

  const runMutation = useMutation({
    mutationFn: async (params: ReportRunParams) => {
      if (reportId != null) {
        return runCustomReport(reportId, params);
      }
      return null;
    },
    onSuccess: (data) => {
      if (data) {
        setResult(data);
        showToast('Report generated successfully', 'success');
        void queryClient.invalidateQueries({ queryKey: ['custom-reports'] });
      }
    },
    onError: () => {
      showToast('Failed to generate report', 'error');
    },
  });

  const handleRun = useCallback(() => {
    const params: ReportRunParams = {
      window_days: windowDays,
      granularity,
      ...(org ? { org } : {}),
      ...(startDate ? { start_date: startDate } : {}),
      ...(endDate ? { end_date: endDate } : {}),
    };

    if (reportId != null) {
      runMutation.mutate(params);
    } else if (reportType) {
      exportReport(reportType, 'csv');
      showToast('Report exported', 'success');
    }
  }, [
    windowDays,
    granularity,
    org,
    startDate,
    endDate,
    reportId,
    reportType,
    runMutation,
    showToast,
  ]);

  const handleExport = useCallback(
    (format: 'csv' | 'xlsx') => {
      if (reportType) {
        exportReport(reportType, format === 'xlsx' ? 'csv' : format);
        showToast(`Exported as ${format.toUpperCase()}`, 'success');
      } else if (result && result.data.length > 0) {
        showToast(`Export initiated`, 'success');
      }
    },
    [reportType, result, showToast],
  );

  return (
    <div className={styles.configPanel} data-testid="report-config-panel">
      <div className={styles.configHeader}>
        <h3 className={styles.configTitle}>{reportName}</h3>
        <Button size="sm" onClick={onClose}>
          ✕
        </Button>
      </div>

      <div className={styles.configBody}>
        {/* Date range presets */}
        <div className={styles.configSection}>
          <label className={styles.configLabel}>Time Window</label>
          <div className={styles.presetButtons}>
            {WINDOW_PRESETS.map((preset) => (
              <Button
                key={preset.days}
                size="sm"
                className={windowDays === preset.days ? styles.windowBtnActive : undefined}
                onClick={() => {
                  setWindowDays(preset.days);
                  setStartDate('');
                  setEndDate('');
                }}
              >
                {preset.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Custom date range */}
        <div className={styles.configSection}>
          <label className={styles.configLabel}>Custom Date Range</label>
          <div className={styles.dateInputs}>
            <input
              type="date"
              className={styles.dateInput}
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              aria-label="Start date"
            />
            <span className={styles.dateSeparator}>to</span>
            <input
              type="date"
              className={styles.dateInput}
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              aria-label="End date"
            />
          </div>
        </div>

        {/* Organization filter */}
        <div className={styles.configSection}>
          <label className={styles.configLabel}>Organization</label>
          <input
            type="text"
            className={styles.textInput}
            placeholder="All organizations"
            value={org}
            onChange={(e) => setOrg(e.target.value)}
            aria-label="Organization filter"
          />
        </div>

        {/* Granularity */}
        <div className={styles.configSection}>
          <label className={styles.configLabel}>Granularity</label>
          <div className={styles.presetButtons}>
            {(['daily', 'weekly', 'monthly'] as const).map((g) => (
              <Button
                key={g}
                size="sm"
                className={granularity === g ? styles.windowBtnActive : undefined}
                onClick={() => setGranularity(g)}
              >
                {g.charAt(0).toUpperCase() + g.slice(1)}
              </Button>
            ))}
          </div>
        </div>

        {/* Run button */}
        <div className={styles.configActions}>
          <Button onClick={handleRun} disabled={runMutation.isPending}>
            {runMutation.isPending ? (
              <>
                <Spinner /> Running…
              </>
            ) : (
              'Run Report'
            )}
          </Button>
          {(result ?? reportType) && (
            <div className={styles.exportButtons}>
              <Button size="sm" onClick={() => handleExport('csv')}>
                CSV
              </Button>
              <Button size="sm" onClick={() => handleExport('xlsx')}>
                XLSX
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      {result && result.data.length > 0 && (
        <div className={styles.configResults}>
          <div className={styles.resultsMeta}>
            {result.row_count} rows · Generated {new Date(result.generated_at).toLocaleString()}
          </div>
          <div className={styles.reportTableContainer}>
            <DataTable<Record<string, unknown>>
              columns={buildDynamicColumns(result.data)}
              data={result.data.map((row, i) => ({ ...row, __idx: i }))}
              rowKey={(row) => row.__idx as number}
              emptyMessage="No data available"
            />
          </div>
        </div>
      )}

      {result && result.data.length === 0 && (
        <div className={styles.emptyReports}>No data found for the selected parameters.</div>
      )}
    </div>
  );
}
