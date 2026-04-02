import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DrilldownModal } from './DrilldownModal';
import type { ColumnDef } from './DataTable';

interface TestRow {
  id: number;
  name: string;
}

const columns: ColumnDef<TestRow>[] = [
  { key: 'id', header: 'ID', render: (r) => String(r.id) },
  { key: 'name', header: 'Name', render: (r) => r.name },
];

const testData: TestRow[] = [
  { id: 1, name: 'Alice' },
  { id: 2, name: 'Bob' },
];

describe('DrilldownModal', () => {
  it('does not render when open is false', () => {
    render(
      <DrilldownModal
        open={false}
        onClose={() => {}}
        title="Test"
        data={testData}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    expect(screen.queryByText('Test')).not.toBeInTheDocument();
  });

  it('renders title when open', () => {
    render(
      <DrilldownModal
        open={true}
        onClose={() => {}}
        title="Test Title"
        data={testData}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    expect(screen.getByText('Test Title')).toBeInTheDocument();
  });

  it('shows spinner when loading', () => {
    render(
      <DrilldownModal
        open={true}
        onClose={() => {}}
        title="Loading Test"
        data={undefined}
        loading={true}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('shows empty message when data is empty array', () => {
    render(
      <DrilldownModal
        open={true}
        onClose={() => {}}
        title="Empty Test"
        data={[]}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    expect(screen.getByText('No items found')).toBeInTheDocument();
  });

  it('shows empty message when data is undefined', () => {
    render(
      <DrilldownModal
        open={true}
        onClose={() => {}}
        title="Undefined Test"
        data={undefined}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    expect(screen.getByText('No items found')).toBeInTheDocument();
  });

  it('renders DataTable rows with data', () => {
    render(
      <DrilldownModal
        open={true}
        onClose={() => {}}
        title="Data Test"
        data={testData}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('renders column headers', () => {
    render(
      <DrilldownModal
        open={true}
        onClose={() => {}}
        title="Headers Test"
        data={testData}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    expect(screen.getByText('ID')).toBeInTheDocument();
    expect(screen.getByText('Name')).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <DrilldownModal
        open={true}
        onClose={onClose}
        title="Close Test"
        data={testData}
        columns={columns}
        rowKey={(r) => r.id}
      />,
    );
    screen.getByLabelText('Close').click();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
