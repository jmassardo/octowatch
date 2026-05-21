import { PageHeader } from '../../components/common/PageHeader';
import { Card } from '../../components/primitives/Card';

export function AuditTrailPage() {
  return (
    <div>
      <PageHeader
        title="Audit Trail"
        description="Track administrative actions and configuration changes."
      />
      <Card>
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <p>Audit Trail is coming soon.</p>
          <p>
            This page will display a log of all administrative actions, configuration changes, and
            access events.
          </p>
        </div>
      </Card>
    </div>
  );
}
