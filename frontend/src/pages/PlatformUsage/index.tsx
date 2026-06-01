import { PageHeader } from '../../components/common/PageHeader';
import { Card } from '../../components/primitives/Card';

export function PlatformUsagePage() {
  return (
    <div>
      <PageHeader
        title="Platform Usage"
        description="Monitor platform resource consumption and API usage metrics."
      />
      <Card>
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <p>Platform Usage monitoring is coming soon.</p>
          <p>
            This page will display API rate limits, storage consumption, and resource utilization.
          </p>
        </div>
      </Card>
    </div>
  );
}
