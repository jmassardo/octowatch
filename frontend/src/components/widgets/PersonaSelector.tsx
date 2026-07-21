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
    id: 'bot',
    label: 'Bot',
    description: 'Automated service accounts and CI/CD integrations.',
    widgetCount: 5,
  },
  {
    id: 'viewer',
    label: 'Viewer',
    description: 'Read-only users who browse repos, issues, and discussions.',
    widgetCount: 4,
  },
  {
    id: 'developer',
    label: 'Developer',
    description: 'Active contributors writing code, opening PRs, and using Copilot.',
    widgetCount: 8,
  },
  {
    id: 'code-reviewer',
    label: 'Code Reviewer',
    description: 'Focus on pull request reviews, approvals, and code quality.',
    widgetCount: 6,
  },
  {
    id: 'product-manager',
    label: 'Product Manager',
    description: 'Manage issues, projects, milestones, and roadmaps.',
    widgetCount: 5,
  },
  {
    id: 'admin',
    label: 'Admin',
    description: 'Organization administration, settings, and access management.',
    widgetCount: 7,
  },
  {
    id: 'collaborator',
    label: 'Collaborator',
    description: 'Cross-functional contributors active across multiple surfaces.',
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
