import { useState, useMemo } from 'react';
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
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
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

  function handleSort(key: string) {
    if (sortColumn === key) {
      if (sortDir === 'asc') {
        setSortDir('desc');
      } else if (sortDir === 'desc') {
        setSortDir(null);
        setSortColumn(null);
      } else {
        setSortDir('asc');
      }
    } else {
      setSortColumn(key);
      setSortDir('asc');
    }
  }

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

  return (
    <div className={`${styles.tableWrap} ${className ?? ''}`}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={col.width ? { width: col.width } : undefined}
                className={col.sortable ? styles.sortable : undefined}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
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
                <th key={`filter-${col.key}`}>
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
        <tbody>
          {sortedData.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className={styles.empty}>
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sortedData.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? styles.clickableRow : undefined}
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
