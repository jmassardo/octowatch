import { Modal } from '../primitives/Modal';
import { Button } from '../primitives/Button';

interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Dialog title. */
  title?: string;
  /** Descriptive message. */
  message?: string;
  /** Text for the confirm button. */
  confirmLabel?: string;
  /** Visual variant of the confirm button. */
  confirmVariant?: 'danger' | 'primary' | 'default';
  /** Callback fired on confirm. */
  onConfirm: () => void;
  /** Callback fired on cancel / close. */
  onCancel: () => void;
  /** Show a loading state on the confirm button. */
  loading?: boolean;
}

/**
 * ConfirmDialog — a modal confirmation prompt for destructive or
 * important actions (delete, disable, revoke).
 *
 * This wraps the existing `Modal` + `Button` primitives so all
 * confirm flows share the same accessible, focus-trapped pattern.
 */
export function ConfirmDialog({
  open,
  title = 'Are you sure?',
  message = 'This action cannot be undone.',
  confirmLabel = 'Confirm',
  confirmVariant = 'danger',
  onConfirm,
  onCancel,
  loading,
}: ConfirmDialogProps) {
  return (
    <Modal open={open} onClose={onCancel} title={title} width={400}>
      <p style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 20, lineHeight: 1.6 }}>
        {message}
      </p>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button variant="default" size="sm" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
        <Button variant={confirmVariant} size="sm" onClick={onConfirm} disabled={loading}>
          {loading ? 'Working…' : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
