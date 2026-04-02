import { Modal } from './Modal';
import { DataTable, type ColumnDef } from './DataTable';
import { Spinner } from './Spinner';

interface DrilldownModalProps<T> {
  open: boolean;
  onClose: () => void;
  title: string;
  data: T[] | undefined;
  loading?: boolean;
  columns: ColumnDef<T>[];
  rowKey: (row: T) => string | number;
}

export function DrilldownModal<T>({
  open,
  onClose,
  title,
  data,
  loading,
  columns,
  rowKey,
}: DrilldownModalProps<T>) {
  return (
    <Modal open={open} onClose={onClose} title={title} width={800}>
      {loading ? (
        <Spinner />
      ) : !data || data.length === 0 ? (
        <div style={{ padding: 24, textAlign: 'center', color: 'var(--fg-muted)' }}>
          No items found
        </div>
      ) : (
        <DataTable columns={columns} data={data} rowKey={rowKey} emptyMessage="No items found" />
      )}
    </Modal>
  );
}
