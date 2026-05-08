import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getEvent } from '../../api/events';
import { EventDetail } from './EventDetail';
import { PageHeader } from '../../components/common/PageHeader';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';

export function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const eventId = Number(id);

  const {
    data: event,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['event', eventId],
    queryFn: () => getEvent(eventId),
    enabled: !Number.isNaN(eventId),
  });

  if (Number.isNaN(eventId)) {
    return (
      <div style={{ padding: '2rem' }}>
        <ErrorBanner message="Invalid event ID" />
        <Link to="/events" style={{ marginTop: 12, display: 'inline-block' }}>
          ← Back to Events
        </Link>
      </div>
    );
  }

  return (
    <div style={{ padding: '0 1.5rem 2rem' }}>
      <PageHeader
        title={event ? `Event #${event.id}` : `Event #${eventId}`}
        description={event?.action}
      />
      <Link to="/events" style={{ fontSize: 13, marginBottom: 16, display: 'inline-block' }}>
        ← Back to Events
      </Link>

      {isLoading && <Spinner />}
      {isError && <ErrorBanner message="Failed to load event" onRetry={refetch} />}
      {event && <EventDetail event={event} />}
    </div>
  );
}
