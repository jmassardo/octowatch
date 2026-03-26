import styles from './Card.module.css';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export function Card({ children, className, style }: CardProps) {
  return (
    <div className={[styles.card, className].filter(Boolean).join(' ')} style={style}>
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
