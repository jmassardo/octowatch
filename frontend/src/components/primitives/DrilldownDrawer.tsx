import { Drawer } from './Drawer';
import { DataTable, type ColumnDef } from './DataTable';
import { Spinner } from './Spinner';

interface DrilldownDrawerProps<T> {
  open: boolean;
  onClose: () => void;
  title: string;
  data: T[] | undefined;
  loading?: boolean;
  columns: ColumnDef<T>[];
  rowKey: (row: T) => string | number;
}

export function DrilldownDrawer<T>({
  open,
  onClose,
  title,
  data,
  loading,
  columns,
  rowKey,
}: DrilldownDrawerProps<T>) {
  return (
    <Drawer open={open} onClose={onClose} title={title}>
      {loading ? (
        <Spinner />
      ) : !data || data.length === 0 ? (
        <div style={{ padding: 24, textAlign: 'center', color: 'var(--fg-muted)' }}>
          No items found
        </div>
      ) : (
        <DataTable columns={columns} data={data} rowKey={rowKey} emptyMessage="No items found" />
      )}
    </Drawer>
  );
}
