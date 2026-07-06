import { PageHeader } from '../../components/common/PageHeader';
import { FeedsTab } from './FeedsTab';
import styles from './ThreatIntel.module.css';

/**
 * Feed detail page rendered at /threat-intel/feeds/:feedId.
 * Reuses FeedsTab which reads feedId from useParams.
 */
export function ThreatIntelFeedDetailPage() {
  return (
    <div className={styles.page}>
      <PageHeader
        title="Threat Intelligence"
        description="Manage threat intelligence feeds, indicators, and view detection matches"
      />
      <FeedsTab />
    </div>
  );
}
