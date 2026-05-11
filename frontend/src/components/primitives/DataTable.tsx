import { useState, useMemo, useCallback, useRef } from 'react';
import styles from './DataTable.module.css';

export type SortDirection = 'asc' | 'desc' | null;

export interface ColumnDef<T> {
  key: string;
  header: string;
  sortable?: boolean;
  filterable?: boolean;
  render: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number | Date | null;
  filterValue?: (row: T) => string;
  width?: string;
  helpText?: string;
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: readonly T[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  emptyMessage?: React.ReactNode;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  onRowClick,
  emptyMessage = 'No data',
  className,
}: DataTableProps<T>) {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({});
  const [activeRowIndex, setActiveRowIndex] = useState<number>(-1);
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  const sortAnnouncementRef = useRef<HTMLDivElement>(null);

  function handleSort(key: string) {
    let newDir: SortDirection;
    let newCol: string | null;

    if (sortColumn === key) {
      if (sortDir === 'asc') {
        newDir = 'desc';
        newCol = key;
      } else if (sortDir === 'desc') {
        newDir = null;
        newCol = null;
      } else {
        newDir = 'asc';
        newCol = key;
      }
    } else {
      newCol = key;
      newDir = 'asc';
    }

    setSortColumn(newCol);
    setSortDir(newDir);

    // Announce sort change to screen readers
    if (sortAnnouncementRef.current) {
      const col = columns.find((c) => c.key === key);
      const dirLabel = newDir === 'asc' ? 'ascending' : newDir === 'desc' ? 'descending' : 'none';
      sortAnnouncementRef.current.textContent = col ? `Sorted by ${col.header}, ${dirLabel}` : '';
    }
  }

  const handleSortKeyDown = useCallback(
    (key: string, e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleSort(key);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sortColumn, sortDir, columns],
  );

  function handleFilter(key: string, value: string) {
    setColumnFilters((prev) => ({ ...prev, [key]: value }));
  }

  const filteredData = useMemo(() => {
    let result = data;
    for (const col of columns) {
      const filterVal = columnFilters[col.key]?.toLowerCase();
      if (!filterVal) continue;
      const getVal =
        col.filterValue ??
        ((row: T) => {
          const node = col.render(row);
          return typeof node === 'string' ? node : '';
        });
      result = result.filter((row) => getVal(row).toLowerCase().includes(filterVal));
    }
    return result;
  }, [data, columns, columnFilters]);

  const sortedData = useMemo(() => {
    if (!sortColumn || !sortDir) return filteredData;
    const col = columns.find((c) => c.key === sortColumn);
    if (!col) return filteredData;
    const getVal =
      col.sortValue ??
      col.filterValue ??
      ((row: T) => {
        const node = col.render(row);
        return typeof node === 'string' ? node : '';
      });
    return [...filteredData].sort((a, b) => {
      const aVal = getVal(a);
      const bVal = getVal(b);
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filteredData, sortColumn, sortDir, columns]);

  const hasFilters = columns.some((c) => c.filterable);

  /** Keyboard navigation for table rows */
  const handleRowKeyDown = useCallback(
    (e: React.KeyboardEvent, row: T, index: number) => {
      if (e.key === 'Enter' && onRowClick) {
        e.preventDefault();
        onRowClick(row);
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const nextIndex = Math.min(index + 1, sortedData.length - 1);
        setActiveRowIndex(nextIndex);
        focusRow(nextIndex);
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prevIndex = Math.max(index - 1, 0);
        setActiveRowIndex(prevIndex);
        focusRow(prevIndex);
        return;
      }
    },
    [onRowClick, sortedData.length],
  );

  function focusRow(index: number) {
    const rows = tbodyRef.current?.querySelectorAll<HTMLElement>('tr[tabindex]');
    rows?.[index]?.focus();
  }

  return (
    <div className={`${styles.tableWrap} ${className ?? ''}`}>
      {/* Screen reader announcement for sort changes */}
      <div ref={sortAnnouncementRef} className="sr-only" aria-live="polite" aria-atomic="true" />
      <table
        className={styles.table}
        aria-rowcount={sortedData.length}
        aria-colcount={columns.length}
      >
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                style={col.width ? { width: col.width } : undefined}
                className={col.sortable ? styles.sortable : undefined}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
                onKeyDown={col.sortable ? (e) => handleSortKeyDown(col.key, e) : undefined}
                tabIndex={col.sortable ? 0 : undefined}
                role={col.sortable ? 'columnheader' : undefined}
                aria-sort={
                  sortColumn === col.key && sortDir === 'asc'
                    ? 'ascending'
                    : sortColumn === col.key && sortDir === 'desc'
                      ? 'descending'
                      : undefined
                }
              >
                <span className={styles.headerContent}>
                  {col.header}
                  {col.helpText && (
                    <span
                      className={styles.helpIcon}
                      title={col.helpText}
                      aria-label={`Help: ${col.header}`}
                    >
                      ⓘ
                    </span>
                  )}
                  {col.sortable && (
                    <span className={styles.sortIcon} aria-hidden="true">
                      {sortColumn === col.key
                        ? sortDir === 'asc'
                          ? '↑'
                          : sortDir === 'desc'
                            ? '↓'
                            : '⇅'
                        : '⇅'}
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
          {hasFilters && (
            <tr className={styles.filterRow} data-testid="filter-row">
              {columns.map((col) => (
                <th scope="col" key={`filter-${col.key}`}>
                  {col.filterable ? (
                    <input
                      className={styles.filterInput}
                      placeholder={`Filter ${col.header.toLowerCase()}...`}
                      value={columnFilters[col.key] ?? ''}
                      onChange={(e) => handleFilter(col.key, e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Filter ${col.header}`}
                    />
                  ) : null}
                </th>
              ))}
            </tr>
          )}
        </thead>
        <tbody ref={tbodyRef}>
          {sortedData.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className={styles.empty}>
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sortedData.map((row, index) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={onRowClick ? (e) => handleRowKeyDown(e, row, index) : undefined}
                className={onRowClick ? styles.clickableRow : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                aria-rowindex={index + 1}
                aria-selected={onRowClick ? activeRowIndex === index : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key}>{col.render(row)}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
