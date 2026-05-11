import { useEffect, useMemo } from 'react';

export interface HotkeyBinding {
  /** Human-readable key combo, e.g. "g d", "?", "Ctrl+K" */
  key: string;
  /** Handler invoked when the shortcut fires. */
  handler: () => void;
  /** Display label for the shortcuts dialog. */
  label: string;
  /** Grouping category for the shortcuts dialog. */
  category: 'Navigation' | 'Actions' | 'General';
  /** If true the shortcut fires even inside inputs (default false). */
  allowInInput?: boolean;
}

interface ParsedChord {
  ctrl: boolean;
  meta: boolean;
  alt: boolean;
  shift: boolean;
  baseKey: string;
}

interface RegistryEntry {
  binding: HotkeyBinding;
  id: number;
}

const registry = new Map<string, RegistryEntry[]>();
const SEQUENCE_TIMEOUT_MS = 1000;
const SHIFT_REQUIRED_PATTERN = /[a-z0-9]/;

let nextId = 0;
let listenerAttached = false;
let pendingPrefix: string | null = null;
let prefixTimer: ReturnType<typeof setTimeout> | null = null;

function parseChord(chord: string): ParsedChord {
  const parts = chord
    .split('+')
    .map((part) => part.trim())
    .filter(Boolean);
  const parsed: ParsedChord = {
    ctrl: false,
    meta: false,
    alt: false,
    shift: false,
    baseKey: '',
  };

  for (const part of parts) {
    const normalized = part.toLowerCase();
    if (normalized === 'ctrl' || normalized === 'control') parsed.ctrl = true;
    else if (normalized === 'meta' || normalized === 'cmd' || normalized === 'command')
      parsed.meta = true;
    else if (normalized === 'alt' || normalized === 'option') parsed.alt = true;
    else if (normalized === 'shift') parsed.shift = true;
    else parsed.baseKey = normalized;
  }

  return parsed;
}

function normalizeKey(key: string): string {
  return key.trim().toLowerCase();
}

function normalizeChord(chord: string): string {
  const parsed = parseChord(chord);
  const parts: string[] = [];

  if (parsed.ctrl) parts.push('ctrl');
  if (parsed.meta) parts.push('meta');
  if (parsed.alt) parts.push('alt');
  if (parsed.shift) parts.push('shift');
  parts.push(parsed.baseKey || normalizeKey(chord));

  return parts.join('+');
}

function normalizeCombo(combo: string): string {
  return combo
    .split(' ')
    .map((chord) => chord.trim())
    .filter(Boolean)
    .map(normalizeChord)
    .join(' ');
}

function eventToChord(event: KeyboardEvent): string {
  const baseKey = normalizeKey(event.key);
  const parts: string[] = [];

  if (event.ctrlKey) parts.push('ctrl');
  if (event.metaKey) parts.push('meta');
  if (event.altKey) parts.push('alt');
  if (event.shiftKey && (baseKey.length > 1 || SHIFT_REQUIRED_PATTERN.test(baseKey))) {
    parts.push('shift');
  }
  parts.push(baseKey);

  return parts.join('+');
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

function getActiveEntry(
  entries: RegistryEntry[] | undefined,
  inEditable: boolean,
): RegistryEntry | undefined {
  return entries?.findLast((entry) => !inEditable || entry.binding.allowInInput);
}

export function registerBinding(binding: HotkeyBinding): number {
  const id = nextId++;
  const normalizedKey = normalizeCombo(binding.key);

  if (import.meta.env.DEV) {
    const existing = registry.get(normalizedKey);
    if (existing?.length) {
      console.warn(
        `[useHotkeys] Duplicate hotkey "${binding.key}" registered. ` +
          `Existing: "${existing[0]!.binding.label}", New: "${binding.label}".`,
      );
    }
  }

  const entries = registry.get(normalizedKey) ?? [];
  entries.push({ binding: { ...binding, key: binding.key.trim() }, id });
  registry.set(normalizedKey, entries);

  return id;
}

export function unregisterBinding(id: number): void {
  for (const [combo, entries] of registry.entries()) {
    const nextEntries = entries.filter((entry) => entry.id !== id);
    if (nextEntries.length !== entries.length) {
      if (nextEntries.length === 0) {
        registry.delete(combo);
      } else {
        registry.set(combo, nextEntries);
      }
      return;
    }
  }
}

export function getBindings(): HotkeyBinding[] {
  return Array.from(registry.values()).flatMap((entries) => entries.map((entry) => entry.binding));
}

function startPrefixTimer(): void {
  clearPrefixTimer();
  prefixTimer = setTimeout(() => {
    pendingPrefix = null;
    prefixTimer = null;
  }, SEQUENCE_TIMEOUT_MS);
}

function clearPrefixTimer(): void {
  if (prefixTimer) {
    clearTimeout(prefixTimer);
    prefixTimer = null;
  }
}

function handleKeyDown(event: KeyboardEvent): void {
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(event.key)) {
    return;
  }

  const inEditable = isEditableTarget(event.target);
  const chord = eventToChord(event);

  if (pendingPrefix) {
    const sequenceEntry = getActiveEntry(registry.get(`${pendingPrefix} ${chord}`), inEditable);
    clearPrefixTimer();
    pendingPrefix = null;

    if (sequenceEntry) {
      event.preventDefault();
      sequenceEntry.binding.handler();
      return;
    }
  }

  const hasSequenceCandidate = Array.from(registry.entries()).some(
    ([combo, entries]) =>
      combo.startsWith(`${chord} `) && Boolean(getActiveEntry(entries, inEditable)),
  );
  if (hasSequenceCandidate) {
    pendingPrefix = chord;
    startPrefixTimer();
    return;
  }

  const entry = getActiveEntry(registry.get(chord), inEditable);
  if (entry) {
    event.preventDefault();
    entry.binding.handler();
  }
}

function ensureListener(): void {
  if (!listenerAttached) {
    document.addEventListener('keydown', handleKeyDown);
    listenerAttached = true;
  }
}

export function useHotkeys(bindings: HotkeyBinding[]): void {
  const normalizedBindings = useMemo(() => bindings, [bindings]);

  useEffect(() => {
    ensureListener();

    const ids = normalizedBindings.map((binding) => registerBinding(binding));

    return () => {
      ids.forEach(unregisterBinding);
    };
  }, [normalizedBindings]);
}

export function useHotkey(
  key: string,
  handler: () => void,
  label: string,
  category: HotkeyBinding['category'] = 'General',
  allowInInput = false,
): void {
  useHotkeys([{ key, handler, label, category, allowInInput }]);
}
