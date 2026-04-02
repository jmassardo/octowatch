import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataTable } from './DataTable';
import type { ColumnDef } from './DataTable';

interface TestRow {
  id: number;
  name: string;
  age: number;
  city: string;
}

const TEST_DATA: TestRow[] = [
  { id: 1, name: 'Alice', age: 30, city: 'New York' },
  { id: 2, name: 'Bob', age: 25, city: 'Chicago' },
  { id: 3, name: 'Charlie', age: 35, city: 'New York' },
  { id: 4, name: 'Diana', age: 28, city: 'Boston' },
];

const COLUMNS: ColumnDef<TestRow>[] = [
  {
    key: 'name',
    header: 'Name',
    sortable: true,
    filterable: true,
    sortValue: (r) => r.name.toLowerCase(),
    filterValue: (r) => r.name,
    render: (r) => r.name,
  },
  {
    key: 'age',
    header: 'Age',
    sortable: true,
    sortValue: (r) => r.age,
    render: (r) => String(r.age),
  },
  {
    key: 'city',
    header: 'City',
    sortable: true,
    filterable: true,
    sortValue: (r) => r.city.toLowerCase(),
    filterValue: (r) => r.city,
    render: (r) => r.city,
  },
];

describe('DataTable', () => {
  /* ---------------------------------------------------------------- */
  /*  Rendering                                                        */
  /* ---------------------------------------------------------------- */

  it('renders a table with column headers', () => {
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    expect(screen.getByRole('table')).toBeInTheDocument();
    // Check header texts (trim sort icons)
    const headerRow = screen.getAllByRole('row')[0];
    const headers = within(headerRow).getAllByRole('columnheader');
    const texts = headers.map((h) => h.textContent?.replace(/[⇅↑↓]/g, '').trim());
    expect(texts).toEqual(['Name', 'Age', 'City']);
  });

  it('renders all data rows', () => {
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Charlie')).toBeInTheDocument();
    expect(screen.getByText('Diana')).toBeInTheDocument();
  });

  it('renders empty message when data is empty', () => {
    render(
      <DataTable
        columns={COLUMNS}
        data={[]}
        rowKey={(r) => r.id}
        emptyMessage="No rows"
      />,
    );

    expect(screen.getByText('No rows')).toBeInTheDocument();
  });

  it('renders default empty message', () => {
    render(
      <DataTable columns={COLUMNS} data={[]} rowKey={(r) => r.id} />,
    );

    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('renders filter inputs for filterable columns', () => {
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    // Name and City are filterable, Age is not
    expect(screen.getByLabelText('Filter Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter City')).toBeInTheDocument();
    expect(screen.queryByLabelText('Filter Age')).not.toBeInTheDocument();
  });

  it('does not render filter row when no columns are filterable', () => {
    const nonFilterableCols: ColumnDef<TestRow>[] = [
      { key: 'name', header: 'Name', render: (r) => r.name },
      { key: 'age', header: 'Age', render: (r) => String(r.age) },
    ];

    render(
      <DataTable
        columns={nonFilterableCols}
        data={TEST_DATA}
        rowKey={(r) => r.id}
      />,
    );

    expect(screen.queryByTestId('filter-row')).not.toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <DataTable
        columns={COLUMNS}
        data={TEST_DATA}
        rowKey={(r) => r.id}
        className="custom-class"
      />,
    );

    expect(container.firstElementChild?.classList.contains('custom-class')).toBe(
      true,
    );
  });

  /* ---------------------------------------------------------------- */
  /*  Sorting                                                          */
  /* ---------------------------------------------------------------- */

  it('sorts ascending on first click', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    // Click Name header to sort asc
    const nameHeader = screen.getByText('Name').closest('th')!;
    await user.click(nameHeader);

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const names = dataRows.map(
      (r) => within(r).getAllByRole('cell')[0].textContent,
    );
    expect(names).toEqual(['Alice', 'Bob', 'Charlie', 'Diana']);
  });

  it('sorts descending on second click', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameHeader = screen.getByText('Name').closest('th')!;
    await user.click(nameHeader); // asc
    await user.click(nameHeader); // desc

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const names = dataRows.map(
      (r) => within(r).getAllByRole('cell')[0].textContent,
    );
    expect(names).toEqual(['Diana', 'Charlie', 'Bob', 'Alice']);
  });

  it('clears sort on third click', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameHeader = screen.getByText('Name').closest('th')!;
    await user.click(nameHeader); // asc
    await user.click(nameHeader); // desc
    await user.click(nameHeader); // none

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const names = dataRows.map(
      (r) => within(r).getAllByRole('cell')[0].textContent,
    );
    // Back to original order
    expect(names).toEqual(['Alice', 'Bob', 'Charlie', 'Diana']);
  });

  it('sorts by numeric column correctly', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const ageHeader = screen.getByText('Age').closest('th')!;
    await user.click(ageHeader); // asc

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const ages = dataRows.map(
      (r) => within(r).getAllByRole('cell')[1].textContent,
    );
    expect(ages).toEqual(['25', '28', '30', '35']);
  });

  it('shows sort direction indicators', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameHeader = screen.getByText('Name').closest('th')!;

    // Initially unsorted
    expect(nameHeader.getAttribute('aria-sort')).toBeNull();

    await user.click(nameHeader);
    expect(nameHeader.getAttribute('aria-sort')).toBe('ascending');
    expect(nameHeader.textContent).toContain('↑');

    await user.click(nameHeader);
    expect(nameHeader.getAttribute('aria-sort')).toBe('descending');
    expect(nameHeader.textContent).toContain('↓');
  });

  it('does not sort non-sortable columns', async () => {
    const user = userEvent.setup();
    const nonSortableCols: ColumnDef<TestRow>[] = [
      { key: 'name', header: 'Name', render: (r) => r.name },
      {
        key: 'age',
        header: 'Age',
        sortable: true,
        sortValue: (r) => r.age,
        render: (r) => String(r.age),
      },
    ];

    render(
      <DataTable
        columns={nonSortableCols}
        data={TEST_DATA}
        rowKey={(r) => r.id}
      />,
    );

    const nameHeader = screen.getByText('Name').closest('th')!;
    await user.click(nameHeader);

    // Should have no sort effect - original order preserved
    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const names = dataRows.map(
      (r) => within(r).getAllByRole('cell')[0].textContent,
    );
    expect(names).toEqual(['Alice', 'Bob', 'Charlie', 'Diana']);
  });

  /* ---------------------------------------------------------------- */
  /*  Filtering                                                        */
  /* ---------------------------------------------------------------- */

  it('filters by text input', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameFilter = screen.getByLabelText('Filter Name');
    await user.type(nameFilter, 'ali');

    // Only Alice should be visible
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.queryByText('Bob')).not.toBeInTheDocument();
    expect(screen.queryByText('Charlie')).not.toBeInTheDocument();
    expect(screen.queryByText('Diana')).not.toBeInTheDocument();
  });

  it('filter is case-insensitive', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const cityFilter = screen.getByLabelText('Filter City');
    await user.type(cityFilter, 'new york');

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Charlie')).toBeInTheDocument();
    expect(screen.queryByText('Bob')).not.toBeInTheDocument();
    expect(screen.queryByText('Diana')).not.toBeInTheDocument();
  });

  it('multiple filters combine (AND logic)', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameFilter = screen.getByLabelText('Filter Name');
    const cityFilter = screen.getByLabelText('Filter City');

    // Filter city to New York (Alice, Charlie)
    await user.type(cityFilter, 'New York');
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Charlie')).toBeInTheDocument();

    // Further filter name to "cha" (only Charlie)
    await user.type(nameFilter, 'cha');
    expect(screen.getByText('Charlie')).toBeInTheDocument();
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
  });

  it('shows empty message when filter matches nothing', async () => {
    const user = userEvent.setup();
    render(
      <DataTable
        columns={COLUMNS}
        data={TEST_DATA}
        rowKey={(r) => r.id}
        emptyMessage="Nothing found"
      />,
    );

    const nameFilter = screen.getByLabelText('Filter Name');
    await user.type(nameFilter, 'zzzzz');

    expect(screen.getByText('Nothing found')).toBeInTheDocument();
  });

  it('clearing filter restores all rows', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameFilter = screen.getByLabelText('Filter Name');
    await user.type(nameFilter, 'alice');

    expect(screen.queryByText('Bob')).not.toBeInTheDocument();

    await user.clear(nameFilter);

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Charlie')).toBeInTheDocument();
    expect(screen.getByText('Diana')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Sort + Filter combined                                           */
  /* ---------------------------------------------------------------- */

  it('sorting works on filtered data', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    // Filter to New York (Alice 30, Charlie 35)
    const cityFilter = screen.getByLabelText('Filter City');
    await user.type(cityFilter, 'New York');

    // Sort by age ascending
    const ageHeader = screen.getByText('Age').closest('th')!;
    await user.click(ageHeader);

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const names = dataRows.map(
      (r) => within(r).getAllByRole('cell')[0].textContent,
    );
    expect(names).toEqual(['Alice', 'Charlie']); // 30 < 35
  });

  /* ---------------------------------------------------------------- */
  /*  Row click                                                        */
  /* ---------------------------------------------------------------- */

  it('calls onRowClick when a row is clicked', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <DataTable
        columns={COLUMNS}
        data={TEST_DATA}
        rowKey={(r) => r.id}
        onRowClick={onClick}
      />,
    );

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    await user.click(dataRows[1]); // Bob

    expect(onClick).toHaveBeenCalledOnce();
    expect(onClick).toHaveBeenCalledWith(TEST_DATA[1]);
  });

  it('does not add clickable styling without onRowClick', () => {
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    for (const row of dataRows) {
      expect(row.classList.contains('clickableRow')).toBe(false);
    }
  });

  /* ---------------------------------------------------------------- */
  /*  Column width                                                     */
  /* ---------------------------------------------------------------- */

  it('applies column width when specified', () => {
    const cols: ColumnDef<TestRow>[] = [
      {
        key: 'name',
        header: 'Name',
        render: (r) => r.name,
        width: '200px',
      },
      {
        key: 'age',
        header: 'Age',
        render: (r) => String(r.age),
      },
    ];

    render(
      <DataTable columns={cols} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameHeader = screen.getByText('Name').closest('th')!;
    expect(nameHeader.style.width).toBe('200px');

    const ageHeader = screen.getByText('Age').closest('th')!;
    expect(ageHeader.style.width).toBe('');
  });

  /* ---------------------------------------------------------------- */
  /*  Null handling in sort                                            */
  /* ---------------------------------------------------------------- */

  it('handles null sort values (pushes to end)', async () => {
    const user = userEvent.setup();
    const dataWithNull: TestRow[] = [
      ...TEST_DATA,
      { id: 5, name: 'Eve', age: 0, city: '' },
    ];

    const colsWithNull: ColumnDef<TestRow>[] = [
      {
        key: 'name',
        header: 'Name',
        sortable: true,
        sortValue: (r) => (r.name === 'Eve' ? null : r.name.toLowerCase()),
        render: (r) => r.name,
      },
      { key: 'age', header: 'Age', render: (r) => String(r.age) },
    ];

    render(
      <DataTable
        columns={colsWithNull}
        data={dataWithNull}
        rowKey={(r) => r.id}
      />,
    );

    const nameHeader = screen.getByText('Name').closest('th')!;
    await user.click(nameHeader); // asc

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const names = dataRows.map(
      (r) => within(r).getAllByRole('cell')[0].textContent,
    );
    // null should be last
    expect(names[names.length - 1]).toBe('Eve');
  });

  /* ---------------------------------------------------------------- */
  /*  Switching sort columns                                           */
  /* ---------------------------------------------------------------- */

  it('resets to ascending when switching sort column', async () => {
    const user = userEvent.setup();
    render(
      <DataTable columns={COLUMNS} data={TEST_DATA} rowKey={(r) => r.id} />,
    );

    const nameHeader = screen.getByText('Name').closest('th')!;
    const ageHeader = screen.getByText('Age').closest('th')!;

    // Sort by name desc
    await user.click(nameHeader); // asc
    await user.click(nameHeader); // desc

    // Switch to age - should start with asc
    await user.click(ageHeader);

    expect(ageHeader.getAttribute('aria-sort')).toBe('ascending');
    expect(nameHeader.getAttribute('aria-sort')).toBeNull();

    const dataRows = screen.getAllByRole('row').filter(
      (r) => within(r).queryAllByRole('cell').length > 0,
    );
    const ages = dataRows.map(
      (r) => within(r).getAllByRole('cell')[1].textContent,
    );
    expect(ages).toEqual(['25', '28', '30', '35']);
  });
});
