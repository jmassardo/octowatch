import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { createPortal } from 'react-dom';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { listEvents } from '../../api/events';
import { listDetections } from '../../api/detections';
import { searchActors } from '../../api/actors';
import type { EventResponse } from '../../types/events';
import type { DetectionResponse } from '../../types/detections';
import { useDebounce } from '../../hooks/useDebounce';
import {
  loadRecentCommandPaletteSearches,
  saveRecentCommandPaletteSearch,
} from '../../hooks/useCommandPalette';
import styles from './CommandPalette.module.css';

type PaletteItem =
  | { id: string; type: 'page' | 'action'; title: string; subtitle: string; to: string }
  | { id: string; type: 'event'; title: string; subtitle: string; eventId: number }
  | { id: string; type: 'detection'; title: string; subtitle: string; detectionId: number }
  | { id: string; type: 'actor'; title: string; subtitle: string; login: string }
  | { id: string; type: 'recent'; title: string; subtitle: string; query: string };

type PaletteGroup = {
  key: string;
  title: string;
  items: PaletteItem[];
  isLoading?: boolean;
};

type SearchableNavigationItem = {
  id: string;
  title: string;
  subtitle: string;
  to: string;
  searchText: string;
};

type RankedNavigationItem = {
  id: string;
  type: 'page' | 'action';
  title: string;
  subtitle: string;
  to: string;
  score: number;
};

const PAGES: SearchableNavigationItem[] = [
  {
    id: 'dashboard',
    title: 'Dashboard',
    subtitle: 'Overview and executive insights',
    to: '/dashboard',
    searchText: 'dashboard overview executive home',
  },
  {
    id: 'threats',
    title: 'Threats',
    subtitle: 'Investigate detections and response workflows',
    to: '/threats',
    searchText: 'threats detections alerts response',
  },
  {
    id: 'events',
    title: 'Events',
    subtitle: 'Browse audit activity',
    to: '/events',
    searchText: 'events audit activity logs',
  },
  {
    id: 'posture',
    title: 'Posture',
    subtitle: 'Security posture and repository controls',
    to: '/posture',
    searchText: 'posture security controls repositories',
  },
  {
    id: 'workflows',
    title: 'Workflows',
    subtitle: 'Workflow security and metrics',
    to: '/workflows',
    searchText: 'workflows workflow security ci cd actions',
  },
  {
    id: 'workflow-health',
    title: 'Workflow Health',
    subtitle: 'Operational workflow health view',
    to: '/workflows/health',
    searchText: 'workflow health operations actions',
  },
  {
    id: 'cross-org',
    title: 'Cross-Org',
    subtitle: 'Cross-organization visibility',
    to: '/crossorg',
    searchText: 'cross-org cross org organizations',
  },
  {
    id: 'copilot',
    title: 'Copilot',
    subtitle: 'Copilot usage and governance',
    to: '/copilot',
    searchText: 'copilot ai assistants governance adoption',
  },
  {
    id: 'velocity',
    title: 'Velocity',
    subtitle: 'Engineering delivery metrics',
    to: '/velocity',
    searchText: 'velocity engineering lead time delivery',
  },
  {
    id: 'reports',
    title: 'Reports',
    subtitle: 'Saved and custom reports',
    to: '/reports',
    searchText: 'reports report builder analytics',
  },
  {
    id: 'compliance',
    title: 'Compliance',
    subtitle: 'Compliance reporting and posture',
    to: '/compliance',
    searchText: 'compliance controls posture evidence',
  },
  {
    id: 'rules',
    title: 'Rules',
    subtitle: 'Detection and policy rules',
    to: '/rules',
    searchText: 'rules detections policies editor',
  },
  {
    id: 'settings',
    title: 'Settings',
    subtitle: 'Configuration and admin controls',
    to: '/settings',
    searchText: 'settings configuration admin features integrations',
  },
  {
    id: 'health',
    title: 'Health',
    subtitle: 'Organization health signals',
    to: '/health',
    searchText: 'health signals security governance repos',
  },
  {
    id: 'threat-intel',
    title: 'Threat Intel',
    subtitle: 'Threat intelligence and external signals',
    to: '/threat-intel',
    searchText: 'threat intel intelligence feeds',
  },
  {
    id: 'query',
    title: 'Query',
    subtitle: 'Run ad-hoc investigations',
    to: '/query',
    searchText: 'query search investigate sql',
  },
  {
    id: 'playbooks',
    title: 'Playbooks',
    subtitle: 'Response playbooks and automation',
    to: '/playbooks',
    searchText: 'playbooks automations response runbooks',
  },
  {
    id: 'supply-chain',
    title: 'Supply Chain',
    subtitle: 'Package and dependency exposure',
    to: '/supply-chain',
    searchText: 'supply chain dependencies packages',
  },
  {
    id: 'dev-activity',
    title: 'Dev Activity',
    subtitle: 'Developer activity and trends',
    to: '/devactivity',
    searchText: 'dev activity engineering productivity',
  },
  {
    id: 'users',
    title: 'Users',
    subtitle: 'User and role management',
    to: '/users',
    searchText: 'users roles access identity',
  },
  {
    id: 'telemetry',
    title: 'Telemetry',
    subtitle: 'Platform telemetry and diagnostics',
    to: '/telemetry',
    searchText: 'telemetry diagnostics logging metrics',
  },
];

const ACTIONS: SearchableNavigationItem[] = [
  {
    id: 'action-go-settings',
    title: 'Go to Settings',
    subtitle: 'Open configuration and admin settings',
    to: '/settings',
    searchText: 'settings configuration admin features',
  },
  {
    id: 'action-view-reports',
    title: 'View Reports',
    subtitle: 'Open the reports workspace',
    to: '/reports',
    searchText: 'reports analytics exports',
  },
  {
    id: 'action-create-rule',
    title: 'Create Rule',
    subtitle: 'Open the rules workspace to create a rule',
    to: '/rules',
    searchText: 'create rule detection policy author',
  },
  {
    id: 'action-review-threats',
    title: 'Review Threats',
    subtitle: 'Jump to active detections and investigations',
    to: '/threats',
    searchText: 'threats detections incidents review',
  },
  {
    id: 'action-open-events',
    title: 'Open Events',
    subtitle: 'Inspect audit events and actor activity',
    to: '/events',
    searchText: 'events audit investigate logs',
  },
];

const DETECTION_SEVERITIES = ['critical', 'high', 'medium', 'low'] as const;

function getShortcutHint() {
  if (typeof navigator === 'undefined') return 'Ctrl+K';
  return /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl+K';
}

function scoreFuzzyMatch(value: string, query: string): number | null {
  const normalizedValue = value.toLowerCase();
  const normalizedQuery = query.trim().toLowerCase();

  if (!normalizedQuery) return 0;

  const directMatchIndex = normalizedValue.indexOf(normalizedQuery);
  if (directMatchIndex >= 0) {
    return 1_000 - directMatchIndex * 5 - (normalizedValue.length - normalizedQuery.length);
  }

  let lastMatchIndex = -1;
  let score = 0;

  for (const character of normalizedQuery) {
    const nextMatchIndex = normalizedValue.indexOf(character, lastMatchIndex + 1);
    if (nextMatchIndex === -1) return null;
    score += nextMatchIndex === lastMatchIndex + 1 ? 10 : 4;
    lastMatchIndex = nextMatchIndex;
  }

  return score - (normalizedValue.length - normalizedQuery.length);
}

function rankNavigationItems(
  items: SearchableNavigationItem[],
  query: string,
  type: 'page' | 'action',
) {
  return items
    .map<RankedNavigationItem | null>((item) => {
      const score = scoreFuzzyMatch(`${item.title} ${item.searchText}`, query);
      return score == null
        ? null
        : {
            id: item.id,
            type,
            title: item.title,
            subtitle: item.subtitle,
            to: item.to,
            score,
          };
    })
    .filter((item): item is RankedNavigationItem => item != null)
    .sort((left, right) => right.score - left.score)
    .map((item) => ({
      id: item.id,
      type: item.type,
      title: item.title,
      subtitle: item.subtitle,
      to: item.to,
    }));
}

function buildEventItems(events: readonly EventResponse[], query: string): PaletteItem[] {
  const normalizedQuery = query.toLowerCase();

  return events
    .filter((event) =>
      [event.action, event.actor, event.repo].some(
        (value) => value != null && value.toLowerCase().includes(normalizedQuery),
      ),
    )
    .map((event) => ({
      id: `event-${event.id}`,
      type: 'event' as const,
      title: event.action,
      subtitle: [event.actor ?? 'Unknown actor', event.repo ?? 'No repository']
        .filter(Boolean)
        .join(' • '),
      eventId: event.id,
    }));
}

function buildDetectionItems(
  detections: readonly DetectionResponse[],
  query: string,
): PaletteItem[] {
  const normalizedQuery = query.toLowerCase();

  return detections
    .filter((detection) => {
      const searchableValues = [detection.rule_name, detection.title, detection.severity];
      return searchableValues.some(
        (value) => value != null && value.toLowerCase().includes(normalizedQuery),
      );
    })
    .map((detection) => ({
      id: `detection-${detection.id}`,
      type: 'detection' as const,
      title: detection.rule_name ?? detection.title,
      subtitle: `${detection.severity.toUpperCase()} • ${detection.repo ?? 'No repository'}`,
      detectionId: detection.id,
    }));
}

function buildActorItems(actors: readonly string[]): PaletteItem[] {
  return actors.map((login) => ({
    id: `actor-${login}`,
    type: 'actor' as const,
    title: login,
    subtitle: 'Actor profile',
    login,
  }));
}

function buildRecentItems(recentSearches: readonly string[], query: string): PaletteItem[] {
  return recentSearches
    .map((entry) => ({
      entry,
      score: scoreFuzzyMatch(entry, query),
    }))
    .filter((entry): entry is { entry: string; score: number } => entry.score != null)
    .sort((left, right) => right.score - left.score)
    .map(({ entry }) => ({
      id: `recent-${entry}`,
      type: 'recent' as const,
      title: entry,
      subtitle: 'Recent search',
      query: entry,
    }));
}

function executeRoute(navigate: ReturnType<typeof useNavigate>, item: PaletteItem) {
  if (item.type === 'page' || item.type === 'action') {
    navigate(item.to);
  } else if (item.type === 'event') {
    navigate(`/events/${item.eventId}`);
  } else if (item.type === 'detection') {
    navigate(`/threats/open?id=${item.detectionId}`);
  } else if (item.type === 'actor') {
    navigate(`/actors/${encodeURIComponent(item.login)}`);
  }
}

export function CommandPalette({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const paletteRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [recentSearches, setRecentSearches] = useState<string[]>(() =>
    loadRecentCommandPaletteSearches(),
  );
  const debouncedQuery = useDebounce(query.trim(), 300);
  const normalizedDebouncedQuery = debouncedQuery.toLowerCase();
  const shortcutHint = getShortcutHint();

  useEffect(() => {
    requestAnimationFrame(() => inputRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  const pages = useMemo(
    () => rankNavigationItems(PAGES, query.trim(), 'page').slice(0, 8),
    [query],
  );
  const actions = useMemo(
    () => rankNavigationItems(ACTIONS, query.trim(), 'action').slice(0, 6),
    [query],
  );
  const recent = useMemo(
    () => buildRecentItems(recentSearches, query.trim()).slice(0, 10),
    [query, recentSearches],
  );

  const eventsQuery = useQuery({
    queryKey: ['command-palette', 'events', debouncedQuery],
    enabled: isOpen && normalizedDebouncedQuery.length > 0,
    queryFn: async () => {
      const [byAction, byActor, byRepo] = await Promise.all([
        listEvents({ action: debouncedQuery, page_size: 6 }),
        listEvents({ actor: debouncedQuery, page_size: 6 }),
        listEvents({ repo: debouncedQuery, page_size: 6 }),
      ]);

      const deduped = new Map<number, EventResponse>();
      [...byAction.items, ...byActor.items, ...byRepo.items].forEach((event) => {
        deduped.set(event.id, event);
      });
      return buildEventItems(Array.from(deduped.values()), normalizedDebouncedQuery).slice(0, 8);
    },
  });

  const detectionsQuery = useQuery({
    queryKey: ['command-palette', 'detections', debouncedQuery],
    enabled: isOpen && normalizedDebouncedQuery.length > 0,
    queryFn: async () => {
      const matchedSeverity = DETECTION_SEVERITIES.find(
        (severity) => severity === normalizedDebouncedQuery,
      );
      const response = await listDetections({
        page_size: 12,
        ...(matchedSeverity ? { severity: matchedSeverity } : {}),
      });
      return buildDetectionItems(response.items, normalizedDebouncedQuery).slice(0, 8);
    },
  });

  const actorsQuery = useQuery({
    queryKey: ['command-palette', 'actors', debouncedQuery],
    enabled: isOpen && normalizedDebouncedQuery.length > 0,
    queryFn: async () => buildActorItems(await searchActors(debouncedQuery)),
  });

  const groups = useMemo<PaletteGroup[]>(() => {
    const nextGroups: PaletteGroup[] = [];

    if (query.trim().length === 0 && recent.length > 0) {
      nextGroups.push({ key: 'recent', title: 'Recent Searches', items: recent });
    } else if (query.trim().length > 0 && recent.length > 0) {
      nextGroups.push({ key: 'recent', title: 'Recent Searches', items: recent.slice(0, 3) });
    }

    if (pages.length > 0) {
      nextGroups.push({ key: 'pages', title: 'Pages', items: pages });
    }
    if (query.trim().length > 0) {
      nextGroups.push({
        key: 'events',
        title: 'Events',
        items: eventsQuery.data ?? [],
        isLoading: eventsQuery.isLoading,
      });
      nextGroups.push({
        key: 'detections',
        title: 'Detections',
        items: detectionsQuery.data ?? [],
        isLoading: detectionsQuery.isLoading,
      });
      nextGroups.push({
        key: 'actors',
        title: 'Actors',
        items: actorsQuery.data ?? [],
        isLoading: actorsQuery.isLoading,
      });
    }
    if (actions.length > 0) {
      nextGroups.push({ key: 'actions', title: 'Actions', items: actions });
    }

    return nextGroups.filter((group) => group.items.length > 0 || group.isLoading);
  }, [
    actions,
    actorsQuery.data,
    actorsQuery.isLoading,
    detectionsQuery.data,
    detectionsQuery.isLoading,
    eventsQuery.data,
    eventsQuery.isLoading,
    pages,
    query,
    recent,
  ]);

  const flatItems = useMemo(() => groups.flatMap((group) => group.items), [groups]);
  const activeItemIndex =
    flatItems.length === 0 ? 0 : Math.min(activeIndex, Math.max(flatItems.length - 1, 0));

  if (!isOpen) return null;

  const isLoadingResults =
    eventsQuery.isLoading || detectionsQuery.isLoading || actorsQuery.isLoading;
  const showEmptyState = query.trim().length > 0 && !isLoadingResults && flatItems.length === 0;

  function closePalette() {
    onClose();
  }

  function handleSelect(item: PaletteItem) {
    if (item.type === 'recent') {
      setQuery(item.query);
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
      return;
    }

    const nextRecentSearches = saveRecentCommandPaletteSearch(query);
    setRecentSearches(nextRecentSearches);
    executeRoute(navigate, item);
    closePalette();
  }

  function handleInputKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (flatItems.length > 0) {
        setActiveIndex((currentIndex) => (currentIndex + 1) % flatItems.length);
      }
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (flatItems.length > 0) {
        setActiveIndex((currentIndex) => (currentIndex - 1 + flatItems.length) % flatItems.length);
      }
      return;
    }

    if (event.key === 'Enter' && flatItems[activeItemIndex]) {
      event.preventDefault();
      handleSelect(flatItems[activeItemIndex]!);
      return;
    }

    if (event.key === 'Escape') {
      event.preventDefault();
      closePalette();
    }
  }

  function handlePaletteKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Tab' || !paletteRef.current) return;

    const focusableElements = Array.from(
      paletteRef.current.querySelectorAll<HTMLElement>('input, button:not([disabled])'),
    );
    if (focusableElements.length === 0) return;

    const firstElement = focusableElements[0]!;
    const lastElement = focusableElements[focusableElements.length - 1]!;

    if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement.focus();
      return;
    }

    if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement.focus();
    }
  }

  return createPortal(
    <div className={styles.backdrop} onClick={closePalette}>
      <div
        ref={paletteRef}
        className={styles.palette}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handlePaletteKeyDown}
      >
        <div className={styles.searchRow}>
          <span className={styles.searchIcon} aria-hidden="true">
            ⌕
          </span>
          <input
            ref={inputRef}
            className={styles.searchInput}
            type="text"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleInputKeyDown}
            placeholder={`Search pages, events, detections, actors… (${shortcutHint})`}
            aria-label="Search command palette"
          />
        </div>

        <div className={styles.results} role="listbox" aria-label="Command palette results">
          {groups.map((group) => (
            <section
              key={group.key}
              className={styles.group}
              aria-labelledby={`command-palette-group-${group.key}`}
            >
              <div className={styles.groupTitle} id={`command-palette-group-${group.key}`}>
                {group.title}
              </div>
              {group.isLoading && group.items.length === 0 ? (
                <div className={styles.emptyGroup}>Searching…</div>
              ) : (
                group.items.map((item) => {
                  const itemIndex = flatItems.findIndex((entry) => entry.id === item.id);
                  const isActive = itemIndex === activeItemIndex;

                  return (
                    <button
                      key={item.id}
                      type="button"
                      role="option"
                      aria-selected={isActive}
                      className={`${styles.resultItem}${isActive ? ` ${styles.resultItemActive}` : ''}`}
                      onMouseEnter={() => setActiveIndex(itemIndex)}
                      onClick={() => handleSelect(item)}
                    >
                      <span className={styles.resultText}>
                        <span className={styles.resultTitle}>{item.title}</span>
                        <span className={styles.resultSubtitle}>{item.subtitle}</span>
                      </span>
                      <span className={styles.resultType}>{group.title}</span>
                    </button>
                  );
                })
              )}
            </section>
          ))}

          {showEmptyState && <div className={styles.emptyState}>No matches found.</div>}
        </div>
      </div>
    </div>,
    document.body,
  );
}
