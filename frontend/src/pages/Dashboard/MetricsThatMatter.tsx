import { useQuery } from '@tanstack/react-query';
import { getMetricsThatMatter } from '../../api/executive';
import type {
  ShippingFasterMetrics,
  ShippingSaferMetrics,
  ShippingCheaperMetrics,
  FasterTrendPoint,
  SaferTrendPoint,
  CheaperTrendPoint,
} from '../../api/executive';
import { Card } from '../../components/primitives/Card';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import styles from './MetricsThatMatter.module.css';

type Period = 7 | 30 | 90;

interface Props {
  period: Period;
  org?: string;
}

// ── Null/tooltip helpers ──────────────────────────────────────────────────────

function MetricValue({
  value,
  formatter,
  tooltip,
  nullReason,
}: {
  value: number | null;
  formatter: (v: number) => string;
  tooltip: string;
  nullReason?: string;
}) {
  const display = value !== null ? formatter(value) : '—';
  const title = value !== null ? tooltip : (nullReason ?? 'No data available for this period');
  return (
    <span className={styles.metricValue} title={title}>
      {display}
    </span>
  );
}

// ── Skeleton loading state ────────────────────────────────────────────────────

function ColumnSkeleton() {
  return (
    <div className={styles.column}>
      <div className={styles.columnHeader}>
        <div className={styles.skeletonTitle} />
      </div>
      {[1, 2, 3].map((i) => (
        <div key={i} className={styles.metricCard}>
          <div className={styles.skeletonLabel} />
          <div className={styles.skeletonValue} />
        </div>
      ))}
      <div className={styles.skeletonChart} />
    </div>
  );
}

// ── Shipping Faster column ────────────────────────────────────────────────────

function ShippingFasterColumn({ data }: { data: ShippingFasterMetrics }) {
  const trendLabels = data.trend.map((p: FasterTrendPoint) => p.date.slice(0, 10));
  const trendHours = data.trend.map((p: FasterTrendPoint) => p.avg_pr_hours ?? 0);
  const hasTrend = trendLabels.length > 0;

  return (
    <div className={styles.column}>
      <div className={styles.columnHeader}>
        <span className={styles.columnIcon} aria-hidden="true">🚀</span>
        <span className={styles.columnTitle}>Shipping Faster</span>
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Avg PR lifecycle
          <span
            className={styles.helpIcon}
            title="Average hours from pull request opened to merged. Derived from pull_request.opened and pull_request.closed (merged=true) audit events. If high: look for review bottlenecks or large PR sizes."
            aria-label="Help: Avg PR lifecycle metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.avg_pr_lifecycle_hours}
          formatter={(v) => `${v.toFixed(1)}h`}
          tooltip="Average time from PR open to merge in hours"
          nullReason="No merged PRs found in this period"
        />
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Deploy frequency
          <span
            className={styles.helpIcon}
            title="Successful workflow runs with 'deploy', 'release', or 'publish' in the name, per week. Derived from workflow_run.completed (conclusion=success) audit events. If low: check CI/CD pipeline frequency."
            aria-label="Help: Deploy frequency metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.deployment_frequency_per_week}
          formatter={(v) => `${v.toFixed(1)}/wk`}
          tooltip="Successful deployments per week"
          nullReason="No deployment workflows found in this period"
        />
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          PR merge rate
          <span
            className={styles.helpIcon}
            title="Percentage of closed pull requests that were merged (vs. abandoned). Derived from pull_request.closed audit events. If low: investigate why PRs are being closed without merging."
            aria-label="Help: PR merge rate metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.pr_merge_rate_pct}
          formatter={(v) => `${v.toFixed(0)}%`}
          tooltip="Percentage of closed PRs that were merged"
          nullReason="No closed PRs found in this period"
        />
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Avg review rounds
          <span
            className={styles.helpIcon}
            title="Average number of review_requested events per PR. Derived from pull_request.review_requested audit events. If high: consider smaller PRs or clearer contribution guidelines."
            aria-label="Help: Avg review rounds metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.avg_pr_review_rounds}
          formatter={(v) => v.toFixed(1)}
          tooltip="Average review request cycles per PR"
          nullReason="No review request events found in this period"
        />
      </div>

      {hasTrend && (
        <div className={styles.chartWrapper}>
          <div className={styles.chartLabel}>PR lifecycle trend</div>
          <LineAreaChart
            xAxisData={trendLabels}
            series={[
              {
                name: 'Avg PR hours',
                data: trendHours,
                color: '#58a6ff',
                areaOpacity: 0.12,
              },
            ]}
            height={100}
          />
        </div>
      )}
      {!hasTrend && (
        <div className={styles.emptyChart}>No trend data yet</div>
      )}
    </div>
  );
}

// ── Shipping Safer column ─────────────────────────────────────────────────────

function ShippingSaferColumn({ data }: { data: ShippingSaferMetrics }) {
  const trendLabels = data.trend.map((p: SaferTrendPoint) => p.date.slice(0, 10));
  const trendSuccess = data.trend.map((p: SaferTrendPoint) => p.success_rate ?? 0);
  const hasTrend = trendLabels.length > 0;

  const alertNetClosed = data.codeql_alerts_closed - data.codeql_alerts_opened;

  return (
    <div className={styles.column}>
      <div className={styles.columnHeader}>
        <span className={styles.columnIcon} aria-hidden="true">🔒</span>
        <span className={styles.columnTitle}>Shipping Safer</span>
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Workflow success rate
          <span
            className={styles.helpIcon}
            title="Percentage of completed workflow runs with conclusion=success. Derived from workflow_run.completed audit events. If low: investigate failing pipelines immediately."
            aria-label="Help: Workflow success rate metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.workflow_success_rate_pct}
          formatter={(v) => `${v.toFixed(1)}%`}
          tooltip="Percentage of workflow runs that completed successfully"
          nullReason="No workflow_run.completed events found in this period"
        />
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          CodeQL alerts (net)
          <span
            className={styles.helpIcon}
            title="Net new CodeQL alerts: opened minus closed/dismissed. Derived from code_scanning_alert.appeared_in_branch and code_scanning_alert.fixed/dismissed audit events. Negative means alerts are being resolved."
            aria-label="Help: CodeQL alerts metric"
          >
            ?
          </span>
        </div>
        <span
          className={[
            styles.metricValue,
            alertNetClosed > 0 ? styles.metricDanger : alertNetClosed < 0 ? styles.metricSuccess : '',
          ].filter(Boolean).join(' ')}
          title={`${data.codeql_alerts_opened} opened, ${data.codeql_alerts_closed} closed`}
        >
          {alertNetClosed > 0 ? `+${alertNetClosed}` : alertNetClosed}
        </span>
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Secret alerts
          <span
            className={styles.helpIcon}
            title="Secret scanning alerts opened this period, with resolved count. Derived from secret_scanning_alert.create and secret_scanning_alert.resolve/revoke audit events. Any unresolved secrets need immediate action."
            aria-label="Help: Secret alerts metric"
          >
            ?
          </span>
        </div>
        <span
          className={[
            styles.metricValue,
            data.secret_alerts_opened > 0 ? styles.metricDanger : styles.metricSuccess,
          ].filter(Boolean).join(' ')}
          title={`${data.secret_alerts_opened} opened, ${data.secret_alerts_resolved} resolved`}
        >
          {data.secret_alerts_opened > 0
            ? `${data.secret_alerts_opened} open`
            : '0 open'}
        </span>
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Change failure rate
          <span
            className={styles.helpIcon}
            title="Percentage of deployment workflow runs that failed or timed out. Derived from workflow_run.completed audit events for deploy/release workflows. If high: strengthen pre-deploy testing."
            aria-label="Help: Change failure rate metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.change_failure_rate_pct}
          formatter={(v) => `${v.toFixed(1)}%`}
          tooltip="Percentage of deployments that failed"
          nullReason="No deployment workflows found in this period"
        />
      </div>

      {hasTrend && (
        <div className={styles.chartWrapper}>
          <div className={styles.chartLabel}>Success rate trend</div>
          <LineAreaChart
            xAxisData={trendLabels}
            series={[
              {
                name: 'Success rate %',
                data: trendSuccess,
                color: '#3fb950',
                areaOpacity: 0.12,
              },
            ]}
            height={100}
          />
        </div>
      )}
      {!hasTrend && (
        <div className={styles.emptyChart}>No trend data yet</div>
      )}
    </div>
  );
}

// ── Shipping Cheaper column ───────────────────────────────────────────────────

function ShippingCheaperColumn({ data }: { data: ShippingCheaperMetrics }) {
  const trendLabels = data.trend.map((p: CheaperTrendPoint) => p.date.slice(0, 10));
  const trendWaste = data.trend.map((p: CheaperTrendPoint) => p.failed_waste_pct ?? 0);
  const hasTrend = trendLabels.length > 0;

  return (
    <div className={styles.column}>
      <div className={styles.columnHeader}>
        <span className={styles.columnIcon} aria-hidden="true">💰</span>
        <span className={styles.columnTitle}>Shipping Cheaper</span>
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Failed run waste
          <span
            className={styles.helpIcon}
            title="Percentage of workflow runs that failed, timed out, or were cancelled. Derived from workflow_run.completed audit events. If high: fix flaky tests and infrastructure issues."
            aria-label="Help: Failed run waste metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.failed_run_waste_pct}
          formatter={(v) => `${v.toFixed(1)}%`}
          tooltip="Percentage of compute minutes spent on failed runs"
          nullReason="No workflow_run.completed events found in this period"
        />
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Rerun rate
          <span
            className={styles.helpIcon}
            title="Percentage of workflow runs that were manual reruns (run_attempt > 1). Derived from workflow_run.completed audit events. If high: address root causes of flaky failures."
            aria-label="Help: Rerun rate metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.rerun_rate_pct}
          formatter={(v) => `${v.toFixed(1)}%`}
          tooltip="Percentage of workflow runs that were reruns"
          nullReason="No rerun data found in this period"
        />
      </div>

      <div className={styles.metricCard}>
        <div className={styles.metricLabel}>
          Automation merge rate
          <span
            className={styles.helpIcon}
            title="Percentage of merged PRs merged by bots (Dependabot, Renovate, etc.). Derived from pull_request.closed audit events. Higher rates indicate good dependency automation."
            aria-label="Help: Automation merge rate metric"
          >
            ?
          </span>
        </div>
        <MetricValue
          value={data.automation_merge_rate_pct}
          formatter={(v) => `${v.toFixed(0)}%`}
          tooltip="Percentage of PRs merged by automation bots"
          nullReason="No merged PRs found in this period"
        />
      </div>

      {data.top_wasteful_workflows.length > 0 && (
        <div className={styles.metricCard}>
          <div className={styles.metricLabel}>
            Top wasteful workflow
            <span
              className={styles.helpIcon}
              title="Workflow with highest failure/cancellation rate. Focus optimization efforts here first."
              aria-label="Help: Top wasteful workflow"
            >
              ?
            </span>
          </div>
          <span
            className={[styles.metricValue, styles.metricSmall].join(' ')}
            title={`${data.top_wasteful_workflows[0].waste_pct.toFixed(1)}% failure rate`}
          >
            {data.top_wasteful_workflows[0].workflow.length > 20
              ? `${data.top_wasteful_workflows[0].workflow.slice(0, 20)}…`
              : data.top_wasteful_workflows[0].workflow}
          </span>
        </div>
      )}

      {hasTrend && (
        <div className={styles.chartWrapper}>
          <div className={styles.chartLabel}>Waste trend</div>
          <LineAreaChart
            xAxisData={trendLabels}
            series={[
              {
                name: 'Failed waste %',
                data: trendWaste,
                color: '#f85149',
                areaOpacity: 0.12,
              },
            ]}
            height={100}
          />
        </div>
      )}
      {!hasTrend && (
        <div className={styles.emptyChart}>No trend data yet</div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function MetricsThatMatter({ period, org }: Props) {
  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['metrics-that-matter', period, org],
    queryFn: () => getMetricsThatMatter(period, org),
    staleTime: 5 * 60_000,
  });

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader}>
        <span className={styles.sectionTitle}>Metrics That Matter</span>
        <span className={styles.sectionSubtitle}>
          Engineering velocity and quality signals derived from audit log events
        </span>
      </div>

      {isLoading && (
        <div className={styles.grid}>
          <ColumnSkeleton />
          <ColumnSkeleton />
          <ColumnSkeleton />
        </div>
      )}

      {isError && (
        <ErrorBanner message="Failed to load Metrics That Matter" onRetry={refetch} />
      )}

      {data && !isLoading && (
        <div className={styles.grid}>
          <Card className={styles.columnCard}>
            <ShippingFasterColumn data={data.shipping_faster} />
          </Card>
          <Card className={styles.columnCard}>
            <ShippingSaferColumn data={data.shipping_safer} />
          </Card>
          <Card className={styles.columnCard}>
            <ShippingCheaperColumn data={data.shipping_cheaper} />
          </Card>
        </div>
      )}
    </div>
  );
}
