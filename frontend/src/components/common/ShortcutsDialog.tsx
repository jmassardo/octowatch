import { useMemo } from 'react';
import { Modal } from '../primitives/Modal';
import type { HotkeyBinding } from '../../hooks/useHotkeys';
import { useHotkeyContext } from '../../contexts/HotkeyContext';
import styles from './ShortcutsDialog.module.css';

interface ShortcutsDialogProps {
  open: boolean;
  onClose: () => void;
}

const CATEGORY_ORDER: HotkeyBinding['category'][] = ['Navigation', 'Actions', 'General'];
const STATIC_BINDINGS: HotkeyBinding[] = [
  { key: 'Escape', handler: () => {}, label: 'Close open dialog or panel', category: 'General' },
];

/** Render a key string like "g d" or "Ctrl+K" into styled keycap elements. */
function KeyCaps({ combo }: { combo: string }) {
  /* Handle sequences like "g d" (space-separated single chars). */
  const parts = combo.split(' ').filter(Boolean);

  return (
    <span className={styles.keys}>
      {parts.map((part, i) => {
        /* Handle modifier combos like "Ctrl+K" */
        const segments = part.split('+');
        return (
          <span key={i} className={styles.keys}>
            {i > 0 && <span className={styles.then}>then</span>}
            {segments.map((seg, j) => (
              <kbd key={j} className={styles.kbd}>
                {formatKeyLabel(seg)}
              </kbd>
            ))}
          </span>
        );
      })}
    </span>
  );
}

function formatKeyLabel(key: string): string {
  const map: Record<string, string> = {
    ctrl: '⌃',
    control: '⌃',
    meta: '⌘',
    cmd: '⌘',
    command: '⌘',
    alt: '⌥',
    option: '⌥',
    shift: '⇧',
    escape: 'Esc',
    '?': '?',
  };
  return map[key.toLowerCase()] ?? key.toUpperCase();
}

export function ShortcutsDialog({ open, onClose }: ShortcutsDialogProps) {
  const { getAll } = useHotkeyContext();

  const grouped = useMemo(() => {
    const registeredBindings = getAll();
    const bindings = [...registeredBindings];
    for (const staticBinding of STATIC_BINDINGS) {
      const alreadyRegistered = registeredBindings.some(
        (binding) => binding.key === staticBinding.key,
      );
      if (!alreadyRegistered) {
        bindings.push(staticBinding);
      }
    }

    const groups = new Map<HotkeyBinding['category'], HotkeyBinding[]>();
    for (const cat of CATEGORY_ORDER) {
      groups.set(cat, []);
    }
    for (const b of bindings) {
      const list = groups.get(b.category);
      if (list) list.push(b);
      else groups.set(b.category, [b]);
    }
    return groups;
  }, [getAll, open]);

  return (
    <Modal open={open} onClose={onClose} title="Keyboard Shortcuts" width={480}>
      <div className={styles.content}>
        {CATEGORY_ORDER.map((category) => {
          const items = grouped.get(category);
          if (!items || items.length === 0) return null;
          return (
            <div key={category}>
              <h3 className={styles.categoryTitle}>{category}</h3>
              <ul className={styles.shortcutList}>
                {items.map((item) => (
                  <li
                    key={`${item.category}-${item.key}-${item.label}`}
                    className={styles.shortcutRow}
                  >
                    <span className={styles.label}>{item.label}</span>
                    <KeyCaps combo={item.key} />
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
