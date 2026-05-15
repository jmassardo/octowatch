import { useState } from 'react';
import { Button } from '../primitives/Button';
import { Modal } from '../primitives/Modal';
import styles from './PersonaSelector.module.css';

export interface PersonaOption {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  readonly widgetCount: number;
}

const PERSONAS: readonly PersonaOption[] = [
  {
    id: 'security-analyst',
    label: 'Security Analyst',
    description: 'Focus on threat detection, alert triage, and security posture.',
    widgetCount: 8,
  },
  {
    id: 'engineering-manager',
    label: 'Engineering Manager',
    description: 'Track team velocity, development health, and Copilot adoption.',
    widgetCount: 6,
  },
  {
    id: 'platform-engineer',
    label: 'Platform Engineer',
    description: 'Monitor workflows, sync health, and operational reliability.',
    widgetCount: 7,
  },
  {
    id: 'executive',
    label: 'Executive',
    description: 'High-level security posture, compliance status, and key metrics.',
    widgetCount: 6,
  },
];

interface PersonaSelectorProps {
  readonly open: boolean;
  readonly onSelect: (personaId: string) => void;
  readonly onSkip: () => void;
}

export function PersonaSelector({ open, onSelect, onSkip }: PersonaSelectorProps) {
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <Modal open={open} onClose={onSkip} title="Welcome — choose your role" width={720}>
      <div className={styles.body}>
        <p className={styles.intro}>
          Select a persona to get started with a recommended dashboard layout. You can always
          customize it later.
        </p>
        <div className={styles.grid}>
          {PERSONAS.map((persona) => (
            <button
              key={persona.id}
              type="button"
              className={[styles.card, selected === persona.id && styles.cardSelected]
                .filter(Boolean)
                .join(' ')}
              onClick={() => setSelected(persona.id)}
              aria-pressed={selected === persona.id}
            >
              <div className={styles.cardTitle}>{persona.label}</div>
              <div className={styles.cardDescription}>{persona.description}</div>
              <div className={styles.cardMeta}>{persona.widgetCount} widgets</div>
            </button>
          ))}
        </div>
        <div className={styles.actions}>
          <Button type="button" variant="default" onClick={onSkip}>
            Skip — start empty
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={selected === null}
            onClick={() => selected && onSelect(selected)}
          >
            Apply layout
          </Button>
        </div>
      </div>
    </Modal>
  );
}
