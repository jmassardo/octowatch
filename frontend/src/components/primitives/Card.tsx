import styles from './Card.module.css';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
}

export function Card({ children, className, style, onClick }: CardProps) {
  return (
    <div
      className={[styles.card, className].filter(Boolean).join(' ')}
      style={style}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export function CardHeader({ children, actions }: CardHeaderProps) {
  return (
    <div className={styles.header}>
      <span>{children}</span>
      {actions && <span className={styles.headerActions}>{actions}</span>}
    </div>
  );
}
