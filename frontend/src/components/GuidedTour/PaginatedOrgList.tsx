import { useMemo, useState } from 'react';
import { Pagination } from '../primitives/Pagination';
import styles from './OnboardingWizard.module.css';

const PAGE_SIZE = 20;

interface PaginatedOrgListProps {
  readonly organizations: readonly string[];
  readonly selectedOrganizations: readonly string[];
  readonly onSelectionChange: (selected: string[]) => void;
}

/**
 * Paginated and searchable organization list for onboarding step 2.
 * Handles large enterprise datasets (500+ orgs) with client-side
 * filtering and pagination. Selection state persists across pages.
 */
export function PaginatedOrgList({
  organizations,
  selectedOrganizations,
  onSelectionChange,
}: PaginatedOrgListProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);

  const filteredOrgs = useMemo(() => {
    if (!searchQuery.trim()) return organizations;
    const query = searchQuery.trim().toLowerCase();
    return organizations.filter((org) => org.toLowerCase().includes(query));
  }, [organizations, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredOrgs.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageOrgs = useMemo(
    () => filteredOrgs.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [filteredOrgs, safePage],
  );

  function handleSearchChange(event: React.ChangeEvent<HTMLInputElement>) {
    setSearchQuery(event.target.value);
    setPage(1);
  }

  function handleToggle(org: string, checked: boolean) {
    if (checked) {
      onSelectionChange([...selectedOrganizations.filter((o) => o !== org), org].sort());
    } else {
      onSelectionChange([...selectedOrganizations.filter((o) => o !== org)]);
    }
  }

  function handleSelectAllVisible() {
    const current = new Set(selectedOrganizations);
    for (const org of pageOrgs) {
      current.add(org);
    }
    onSelectionChange([...current].sort());
  }

  function handleDeselectAllVisible() {
    const toRemove = new Set(pageOrgs);
    onSelectionChange(selectedOrganizations.filter((o) => !toRemove.has(o)));
  }

  const allVisibleSelected =
    pageOrgs.length > 0 && pageOrgs.every((o) => selectedOrganizations.includes(o));

  return (
    <div className={styles.paginatedList}>
      <div className={styles.searchRow}>
        <input
          type="search"
          className={styles.searchInput}
          placeholder="Search organizations…"
          value={searchQuery}
          onChange={handleSearchChange}
          aria-label="Search organizations"
        />
        <span className={styles.resultCount}>
          {filteredOrgs.length} org{filteredOrgs.length !== 1 ? 's' : ''}
          {selectedOrganizations.length > 0 && ` · ${selectedOrganizations.length} selected`}
        </span>
      </div>

      <div className={styles.bulkActions}>
        <button
          type="button"
          className={styles.linkButton}
          onClick={allVisibleSelected ? handleDeselectAllVisible : handleSelectAllVisible}
        >
          {allVisibleSelected ? 'Deselect all on page' : 'Select all on page'}
        </button>
      </div>

      {pageOrgs.length === 0 ? (
        <div className={styles.emptyState}>
          {searchQuery.trim()
            ? `No organizations matching "${searchQuery.trim()}"`
            : 'No organizations available.'}
        </div>
      ) : (
        <div className={styles.checklist}>
          {pageOrgs.map((org) => {
            const checked = selectedOrganizations.includes(org);
            return (
              <label key={org} className={styles.checkboxRow}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => handleToggle(org, event.target.checked)}
                />
                <span className={styles.checkboxText}>
                  <strong>{org}</strong>
                  <span>
                    Include activity from this organization in your default monitoring scope.
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      )}

      <Pagination
        page={safePage}
        pageSize={PAGE_SIZE}
        total={filteredOrgs.length}
        onPageChange={setPage}
      />

      <span className={styles.helper}>Select at least one organization to continue.</span>
    </div>
  );
}
