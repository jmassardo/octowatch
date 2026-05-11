import type { MouseEvent } from 'react';

interface SkipToContentProps {
  targetId?: string;
  label?: string;
  className?: string;
}

export function SkipToContent({
  targetId = 'main-content',
  label = 'Skip to main content',
  className = 'skip-to-content',
}: SkipToContentProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    const target = document.getElementById(targetId);

    if (!target) {
      return;
    }

    event.preventDefault();

    const hadTabIndex = target.hasAttribute('tabindex');
    if (target.tabIndex < 0) {
      target.setAttribute('tabindex', '-1');
    }

    target.focus();

    if (!hadTabIndex) {
      target.addEventListener(
        'blur',
        () => {
          target.removeAttribute('tabindex');
        },
        { once: true },
      );
    }

    window.history.replaceState(null, '', `#${targetId}`);
  }

  return (
    <a href={`#${targetId}`} className={className} onClick={handleClick}>
      {label}
    </a>
  );
}
