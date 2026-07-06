import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import styles from './InfoTooltip.module.css';

interface InfoTooltipProps {
  content: string;
  label?: string;
  className?: string;
}

function renderFormattedText(content: string) {
  const linkPattern = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g;

  const parts: ReactNode[] = [];
  let linkMatch: RegExpExecArray | null;
  let lastIndex = 0;

  const renderBoldText = (text: string, keyPrefix: string) => {
    const boldPattern = /\*\*([^*]+)\*\*/g;
    const boldParts: ReactNode[] = [];
    let boldMatch: RegExpExecArray | null;
    let boldLastIndex = 0;

    while ((boldMatch = boldPattern.exec(text)) !== null) {
      if (boldMatch.index > boldLastIndex) {
        boldParts.push(text.slice(boldLastIndex, boldMatch.index));
      }

      boldParts.push(<strong key={`${keyPrefix}-bold-${boldMatch.index}`}>{boldMatch[1]}</strong>);
      boldLastIndex = boldMatch.index + boldMatch[0].length;
    }

    if (boldLastIndex < text.length) {
      boldParts.push(text.slice(boldLastIndex));
    }

    return boldParts;
  };

  while ((linkMatch = linkPattern.exec(content)) !== null) {
    if (linkMatch.index > lastIndex) {
      parts.push(...renderBoldText(content.slice(lastIndex, linkMatch.index), `text-${lastIndex}`));
    }

    parts.push(
      <a key={`link-${linkMatch.index}`} href={linkMatch[2]} target="_blank" rel="noreferrer">
        {linkMatch[1]}
      </a>,
    );
    lastIndex = linkMatch.index + linkMatch[0].length;
  }

  if (lastIndex < content.length) {
    parts.push(...renderBoldText(content.slice(lastIndex), `text-${lastIndex}`));
  }

  return parts;
}

export function InfoTooltip({ content, label = 'More information', className }: InfoTooltipProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  const formattedContent = useMemo(() => renderFormattedText(content), [content]);

  useEffect(() => {
    if (!open || !triggerRef.current || !tooltipRef.current) return;

    const tooltip = tooltipRef.current;
    const triggerRect = triggerRef.current.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const gap = 12;

    const fitsTop = triggerRect.top >= tooltipRect.height + gap;
    const fitsBottom = window.innerHeight - triggerRect.bottom >= tooltipRect.height + gap;
    const fitsRight = window.innerWidth - triggerRect.right >= tooltipRect.width + gap;

    let nextPlacement = 'left';
    if (fitsTop) {
      nextPlacement = 'top';
    } else if (fitsBottom) {
      nextPlacement = 'bottom';
    } else if (fitsRight) {
      nextPlacement = 'right';
    }

    let top: number;
    let left: number;

    if (nextPlacement === 'top') {
      top = triggerRect.top - tooltipRect.height - gap;
      left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
    } else if (nextPlacement === 'bottom') {
      top = triggerRect.bottom + gap;
      left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
    } else if (nextPlacement === 'right') {
      top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2;
      left = triggerRect.right + gap;
    } else {
      top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2;
      left = triggerRect.left - tooltipRect.width - gap;
    }

    tooltip.dataset.placement = nextPlacement;
    tooltip.style.top = `${Math.max(8, Math.min(top, window.innerHeight - tooltipRect.height - 8))}px`;
    tooltip.style.left = `${Math.max(8, Math.min(left, window.innerWidth - tooltipRect.width - 8))}px`;
  }, [open]);

  return (
    <span className={[styles.wrapper, className].filter(Boolean).join(' ')}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        aria-label={label}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        data-testid="info-tooltip-trigger"
      >
        i
      </button>
      {open &&
        createPortal(
          <div
            ref={tooltipRef}
            className={styles.tooltip}
            role="tooltip"
            data-placement="top"
            data-testid="info-tooltip-panel"
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
          >
            {formattedContent}
          </div>,
          document.body,
        )}
    </span>
  );
}
