import { PageHeader } from '../../components/common/PageHeader';
import { DeliveryTimelinePane } from './DeliveryTimelinePane';
import styles from './DeliveryTimeline.module.css';

export function DeliveryTimelinePage() {
  return (
    <div className={styles.page}>
      <PageHeader
        title="Delivery Timeline"
        description="How long pull requests take to move through backlog, development, review, and deployment"
      />
      <DeliveryTimelinePane />
    </div>
  );
}
