import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMe } from '../../api/auth';
import { Button } from '../primitives/Button';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Modal } from '../primitives/Modal';
import {
  PERSONA_WIDGET_PRESETS,
  WIDGET_CATEGORY_LABELS,
  WIDGET_REGISTRY,
  type DashboardPersona,
} from '../widgets/WidgetRegistry';
import { persistOnboardingResult } from './onboardingStorage';
import styles from './OnboardingWizard.module.css';

export interface OnboardingNotifications {
  readonly email: boolean;
  readonly slack: boolean;
  readonly dailyDigest: boolean;
}

export interface OnboardingResult {
  readonly persona: DashboardPersona;
  readonly organizations: readonly string[];
  readonly widgetIds: readonly string[];
  readonly notifications: OnboardingNotifications;
}

interface OnboardingWizardProps {
  readonly open?: boolean;
  readonly availableOrganizations?: readonly string[];
  readonly onComplete: (result: OnboardingResult) => void;
  readonly onClose?: () => void;
}

interface PersonaOption {
  readonly id: DashboardPersona;
  readonly title: string;
  readonly description: string;
  readonly focus: string;
}

const PERSONAS: readonly PersonaOption[] = [
  {
    id: 'security-analyst',
    title: 'Security Analyst',
    description: 'Prioritize detections, active alerts, and threat context for rapid triage.',
    focus: 'Threats and exposure',
  },
  {
    id: 'devops-engineer',
    title: 'DevOps Engineer',
    description: 'Track sync health, event flow, and the operational signals behind delivery.',
    focus: 'Platform reliability',
  },
  {
    id: 'engineering-lead',
    title: 'Engineering Lead',
    description: 'Blend adoption, exposure, and activity trends into a leadership snapshot.',
    focus: 'Team performance and risk',
  },
];

const NOTIFICATION_OPTIONS = [
  {
    id: 'email' as const,
    title: 'Email digests',
    description: 'Receive a daily summary of the dashboard signals you selected.',
  },
  {
    id: 'slack' as const,
    title: 'Slack nudges',
    description: 'Send important dashboard changes to your team channel.',
  },
  {
    id: 'dailyDigest' as const,
    title: 'Morning briefing',
    description: 'Pin a morning briefing with overnight changes and recommended follow-up.',
  },
];

export function OnboardingWizard({
  open = true,
  availableOrganizations,
  onComplete,
  onClose,
}: OnboardingWizardProps) {
  const [step, setStep] = useState(0);
  const [persona, setPersona] = useState<DashboardPersona>('security-analyst');
  const [selectedOrganizations, setSelectedOrganizations] = useState<string[] | null>(null);
  const [selectedWidgetIds, setSelectedWidgetIds] = useState<string[]>([
    ...PERSONA_WIDGET_PRESETS['security-analyst'],
  ]);
  const [notifications, setNotifications] = useState<OnboardingNotifications>({
    email: true,
    slack: false,
    dailyDigest: false,
  });

  const meQuery = useQuery({
    queryKey: ['onboarding', 'me'],
    queryFn: getMe,
    enabled: open && availableOrganizations == null,
    staleTime: 5 * 60 * 1000,
  });

  const organizationOptions = useMemo(
    () => [...(availableOrganizations ?? meQuery.data?.scoped_orgs ?? [])].sort(),
    [availableOrganizations, meQuery.data?.scoped_orgs],
  );
  const organizationSelection = selectedOrganizations ?? organizationOptions;

  if (!open) return null;

  const stepMeta = [
    {
      title: 'Welcome to your dashboard',
      description: 'Choose the persona that best matches how you want Octowatch to guide your day.',
      content: (
        <div className={styles.personaGrid}>
          {PERSONAS.map((option) => (
            <button
              key={option.id}
              type="button"
              className={[styles.cardOption, persona === option.id && styles.cardOptionSelected]
                .filter(Boolean)
                .join(' ')}
              onClick={() => {
                setPersona(option.id);
                setSelectedWidgetIds([...PERSONA_WIDGET_PRESETS[option.id]]);
              }}
            >
              <h3>{option.title}</h3>
              <p>{option.description}</p>
              <span className={styles.optionMeta}>Best for: {option.focus}</span>
            </button>
          ))}
        </div>
      ),
    },
    {
      title: 'Select organizations to monitor',
      description:
        'Start with the orgs you want in focus. You can change this later from the top bar.',
      content:
        meQuery.isError && availableOrganizations == null ? (
          <ErrorBanner
            message="Failed to load organizations"
            onRetry={() => void meQuery.refetch()}
          />
        ) : meQuery.isLoading && availableOrganizations == null ? (
          <div className={styles.emptyState}>Loading organizations…</div>
        ) : organizationOptions.length === 0 ? (
          <div className={styles.emptyState}>
            No scoped organizations were available for onboarding.
          </div>
        ) : (
          <div className={styles.checklist}>
            {organizationOptions.map((org) => {
              const checked = organizationSelection.includes(org);
              return (
                <label key={org} className={styles.checkboxRow}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      const base = selectedOrganizations ?? organizationOptions;
                      setSelectedOrganizations(
                        event.target.checked
                          ? [...base.filter((entry) => entry !== org), org].sort()
                          : base.filter((entry) => entry !== org),
                      );
                    }}
                  />
                  <span className={styles.checkboxText}>
                    <strong>{org}</strong>
                    <span>
                      Include activity from this organization in your default monitoring scope.
                    </span>
                  </span>
                </label>
              );
            })}
            <span className={styles.helper}>Select at least one organization to continue.</span>
          </div>
        ),
    },
    {
      title: 'Pick your starting widgets',
      description:
        'We pre-populated this list from your persona. Add or remove widgets before landing on your dashboard.',
      content: (
        <div className={styles.widgetGrid}>
          {Object.entries(WIDGET_CATEGORY_LABELS).map(([category, label]) => (
            <div key={category} className={styles.cardOption}>
              <h4>{label}</h4>
              <div className={styles.checklist}>
                {WIDGET_REGISTRY.filter((widget) => widget.category === category).map((widget) => (
                  <label key={widget.id} className={styles.checkboxRow}>
                    <input
                      type="checkbox"
                      checked={selectedWidgetIds.includes(widget.id)}
                      onChange={(event) => {
                        setSelectedWidgetIds((current) =>
                          event.target.checked
                            ? [...current.filter((entry) => entry !== widget.id), widget.id]
                            : current.filter((entry) => entry !== widget.id),
                        );
                      }}
                    />
                    <span className={styles.checkboxText}>
                      <strong>{widget.title}</strong>
                      <span>{widget.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      ),
    },
    {
      title: 'Notification preferences',
      description: 'These are optional and only shape your onboarding profile for now.',
      content: (
        <div className={styles.checklist}>
          {NOTIFICATION_OPTIONS.map((option) => (
            <label key={option.id} className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={notifications[option.id]}
                onChange={(event) => {
                  setNotifications((current) => ({
                    ...current,
                    [option.id]: event.target.checked,
                  }));
                }}
              />
              <span className={styles.checkboxText}>
                <strong>{option.title}</strong>
                <span>{option.description}</span>
              </span>
            </label>
          ))}
        </div>
      ),
    },
  ] as const;

  const currentStep = stepMeta[step];
  const canContinue =
    step === 1
      ? organizationOptions.length === 0 || organizationSelection.length > 0
      : step === 2
        ? selectedWidgetIds.length > 0
        : true;

  function handleFinish() {
    const result: OnboardingResult = {
      persona,
      organizations: organizationSelection,
      widgetIds: selectedWidgetIds,
      notifications,
    };

    persistOnboardingResult(result);
    onComplete(result);
  }

  return (
    <Modal open={open} onClose={onClose ?? (() => {})} title="Octowatch onboarding" width={920}>
      <div className={styles.wrapper}>
        <div className={styles.stepHeader}>
          <div>
            <h2 className={styles.stepTitle}>{currentStep.title}</h2>
            <p className={styles.stepDescription}>{currentStep.description}</p>
          </div>
          <div className={styles.progress}>
            Step {step + 1} of {stepMeta.length}
          </div>
        </div>

        {currentStep.content}

        <div className={styles.footer}>
          <div className={styles.helper}>
            Persona preset: {PERSONAS.find((option) => option.id === persona)?.title}
          </div>
          <div className={styles.footerRight}>
            {step > 0 && (
              <Button type="button" onClick={() => setStep((current) => current - 1)}>
                Back
              </Button>
            )}
            {step < stepMeta.length - 1 ? (
              <Button
                type="button"
                variant="primary"
                disabled={!canContinue}
                onClick={() => setStep((current) => current + 1)}
              >
                Next
              </Button>
            ) : (
              <Button
                type="button"
                variant="primary"
                disabled={!canContinue}
                onClick={handleFinish}
              >
                Launch dashboard
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
