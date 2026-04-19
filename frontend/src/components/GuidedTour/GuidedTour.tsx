import { useCallback, useEffect, useState } from 'react';
import styles from './GuidedTour.module.css';

const TOUR_STORAGE_KEY = 'octowatch_tour_completed';

export interface TourStep {
  /** CSS selector for the element to highlight */
  readonly target: string;
  /** Title of the step */
  readonly title: string;
  /** Description text */
  readonly description: string;
}

const TOUR_STEPS: readonly TourStep[] = [
  {
    target: '[href="/dashboard"]',
    title: 'Dashboard',
    description:
      'Your security command center. See threat summaries, event volume, and key metrics at a glance.',
  },
  {
    target: '[href="/threats"]',
    title: 'Threat Detections',
    description:
      'Detection alerts appear here. Review, triage, and investigate security findings from your audit logs.',
  },
  {
    target: '[href="/rules"]',
    title: 'Detection Rules',
    description:
      'Enable detection rules to get started. Browse the Rule Library for 20+ pre-built rules across 6 categories.',
  },
  {
    target: '[href="/health"]',
    title: 'Org Health',
    description:
      "Monitor your organization's security posture. Track PAT hygiene, stale repos, and compliance scores.",
  },
  {
    target: '[href="/query"]',
    title: 'Query Explorer',
    description:
      'Run ad-hoc SQL queries against your audit data. Investigate incidents and generate custom reports.',
  },
  {
    target: '[href="/settings"]',
    title: 'Settings',
    description:
      'Configure integrations, data retention, notifications, and more. Connect Slack, Jira, or SIEM tools.',
  },
];

function getTooltipPosition(rect: DOMRect): { top: number; left: number; placement: string } {
  const tooltipWidth = 340;
  const tooltipHeight = 180;
  const margin = 16;

  // Try right side first
  if (rect.right + margin + tooltipWidth < window.innerWidth) {
    return {
      top: Math.max(margin, rect.top + rect.height / 2 - tooltipHeight / 2),
      left: rect.right + margin,
      placement: 'right',
    };
  }

  // Try left side
  if (rect.left - margin - tooltipWidth > 0) {
    return {
      top: Math.max(margin, rect.top + rect.height / 2 - tooltipHeight / 2),
      left: rect.left - margin - tooltipWidth,
      placement: 'left',
    };
  }

  // Fall back to below
  return {
    top: rect.bottom + margin,
    left: Math.max(margin, rect.left + rect.width / 2 - tooltipWidth / 2),
    placement: 'bottom',
  };
}

export function GuidedTour({ onComplete }: { onComplete?: () => void }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [visible, setVisible] = useState(true);

  const step = TOUR_STEPS[currentStep];

  // Measure target element position. Returns a fresh rect from the DOM.
  const measureTarget = useCallback((): DOMRect | null => {
    if (!step) return null;
    const el = document.querySelector(step.target);
    return el ? el.getBoundingClientRect() : null;
  }, [step]);

  // Keep target rect in state; initialized lazily and updated on layout events.
  const [targetRect, setTargetRect] = useState<DOMRect | null>(() => measureTarget());

  // Re-measure when the step changes
  useEffect(() => {
    setTargetRect(measureTarget());
  }, [measureTarget]);

  // Subscribe to resize/scroll for live position updates
  useEffect(() => {
    const onLayout = () => setTargetRect(measureTarget());
    window.addEventListener('resize', onLayout);
    window.addEventListener('scroll', onLayout, true);
    return () => {
      window.removeEventListener('resize', onLayout);
      window.removeEventListener('scroll', onLayout, true);
    };
  }, [measureTarget]);

  const handleComplete = useCallback(() => {
    localStorage.setItem(TOUR_STORAGE_KEY, 'true');
    setVisible(false);
    onComplete?.();
  }, [onComplete]);

  const handleNext = useCallback(() => {
    if (currentStep < TOUR_STEPS.length - 1) {
      setCurrentStep((prev) => prev + 1);
    } else {
      handleComplete();
    }
  }, [currentStep, handleComplete]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleComplete();
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        handleNext();
      } else if (e.key === 'ArrowLeft' && currentStep > 0) {
        setCurrentStep((prev) => prev - 1);
      }
    },
    [handleComplete, handleNext, currentStep],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!visible || !step || !targetRect) return null;

  const tooltipPos = getTooltipPosition(targetRect);
  const padding = 6;

  return (
    <div className={styles.overlay} role="dialog" aria-label="Guided tour" aria-modal="true">
      {/* SVG overlay with cutout for highlighted element */}
      <svg className={styles.svgOverlay} aria-hidden="true">
        <defs>
          <mask id="tour-mask">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            <rect
              x={targetRect.left - padding}
              y={targetRect.top - padding}
              width={targetRect.width + padding * 2}
              height={targetRect.height + padding * 2}
              rx="8"
              fill="black"
            />
          </mask>
        </defs>
        <rect
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="rgba(0, 0, 0, 0.6)"
          mask="url(#tour-mask)"
        />
      </svg>

      {/* Spotlight border around target */}
      <div
        className={styles.spotlight}
        style={{
          top: targetRect.top - padding,
          left: targetRect.left - padding,
          width: targetRect.width + padding * 2,
          height: targetRect.height + padding * 2,
        }}
      />

      {/* Tooltip */}
      <div
        className={`${styles.tooltip} ${styles[`tooltip${tooltipPos.placement.charAt(0).toUpperCase()}${tooltipPos.placement.slice(1)}`]}`}
        style={{ top: tooltipPos.top, left: tooltipPos.left }}
        role="alertdialog"
        aria-label={step.title}
      >
        <div className={styles.tooltipHeader}>
          <span className={styles.tooltipStep}>
            {currentStep + 1} of {TOUR_STEPS.length}
          </span>
          <button
            className={styles.tooltipClose}
            onClick={handleComplete}
            aria-label="Close tour"
            type="button"
          >
            ×
          </button>
        </div>
        <h3 className={styles.tooltipTitle}>{step.title}</h3>
        <p className={styles.tooltipDescription}>{step.description}</p>
        <div className={styles.tooltipFooter}>
          {currentStep > 0 && (
            <button
              className={styles.tooltipBtnSecondary}
              onClick={() => setCurrentStep((prev) => prev - 1)}
              type="button"
            >
              Back
            </button>
          )}
          <button className={styles.tooltipBtnPrimary} onClick={handleNext} type="button">
            {currentStep < TOUR_STEPS.length - 1 ? 'Next' : 'Get Started'}
          </button>
        </div>
        <div className={styles.tooltipDots}>
          {TOUR_STEPS.map((_, idx) => (
            <span
              key={idx}
              className={`${styles.dot} ${idx === currentStep ? styles.dotActive : ''}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
