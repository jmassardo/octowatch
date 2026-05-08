import { Button } from '../primitives/Button';
import { HelpPanel } from './HelpPanel';
import { useHelp } from '../../hooks/useHelp';
import styles from './PageHeader.module.css';

export interface PageAction {
  label: string;
  onClick: () => void;
  variant?: 'default' | 'primary' | 'danger';
  disabled?: boolean;
}

export interface Breadcrumb {
  label: string;
  href?: string;
}

interface PageHeaderProps {
  /** Page title. */
  title: string;
  /** Optional subtitle / description. */
  description?: string;
  /** Action buttons rendered on the right side. */
  actions?: PageAction[];
  /** Breadcrumb trail above the title. */
  breadcrumbs?: Breadcrumb[];
  /** Show contextual help for the current page. */
  showHelp?: boolean;
}

function PageHeaderHelp() {
  const { helpContent, openHelp, closeHelp, isHelpOpen } = useHelp();

  if (!helpContent) {
    return null;
  }

  return (
    <>
      <Button
        size="sm"
        className={styles.helpButton}
        onClick={openHelp}
        aria-label="Open help panel"
      >
        ?
      </Button>
      <HelpPanel open={isHelpOpen} onClose={closeHelp} content={helpContent} />
    </>
  );
}

/**
 * PageHeader — consistent page header with title, description,
 * optional breadcrumbs, and action buttons.
 */
export function PageHeader({ title, description, actions, breadcrumbs, showHelp }: PageHeaderProps) {
  const hasRightContent = showHelp || (actions && actions.length > 0);

  return (
    <div className={styles.header}>
      <div className={styles.left}>
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav className={styles.breadcrumbs} aria-label="Breadcrumb">
            {breadcrumbs.map((bc, i) => (
              <span key={i}>
                {i > 0 && <span className={styles.separator}>/</span>}
                {bc.href ? <a href={bc.href}>{bc.label}</a> : <span>{bc.label}</span>}
              </span>
            ))}
          </nav>
        )}
        <h1 className={styles.title}>{title}</h1>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      {hasRightContent && (
        <div className={styles.right}>
          {showHelp && <PageHeaderHelp />}
          {actions && actions.length > 0 && (
            <div className={styles.actions}>
              {actions.map((action) => (
                <Button
                  key={action.label}
                  variant={action.variant ?? 'default'}
                  size="sm"
                  onClick={action.onClick}
                  disabled={action.disabled}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
