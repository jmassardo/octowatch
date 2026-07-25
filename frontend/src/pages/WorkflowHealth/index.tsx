import { Link } from 'react-router';
import { PageHeader } from '../../components/common/PageHeader';
import { WorkflowMetricsTab } from '../Workflows/WorkflowMetricsTab';
import styles from './WorkflowHealth.module.css';

export function WorkflowHealthPage() {
  return (
    <div className={styles.page}>
      <PageHeader
        title="Workflow Health"
        description="Operational health of CI/CD workflows — persistent failures and timeouts"
      />

      <div className={styles.crossLink}>
        Looking for security findings?{' '}
        <Link to="/workflows" className={styles.crossLinkAnchor}>
          Workflow Security →
        </Link>
      </div>

      <div className={styles.guidanceBox}>
        <div className={styles.guidanceTitle}>What this page shows</div>
        <ul className={styles.guidanceList}>
          <li>
            <strong>Always Failing</strong> — Workflows that have failed consecutively beyond the
            configured threshold. These may indicate broken pipelines requiring attention.
          </li>
          <li>
            <strong>Always Timing Out</strong> — Workflows that have timed out consecutively. These
            may indicate resource constraints or infinite loops.
          </li>
          <li>
            This page is about <strong>operational failures</strong>, not security. For security
            findings in workflow YAML files, visit{' '}
            <Link to="/workflows" className={styles.crossLinkAnchor}>
              Workflow Security
            </Link>
            .
          </li>
        </ul>
      </div>

      <WorkflowMetricsTab />
    </div>
  );
}
