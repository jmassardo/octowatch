import styles from './Card.module.css';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export function Card({ children, className, style, onClick, ...props }: CardProps) {
  return (
    <div
      {...props}
      className={[styles.card, className].filter(Boolean).join(' ')}
      style={style}
      onClick={onClick}
      role={onClick ? 'button' : props.role}
      tabIndex={onClick ? 0 : props.tabIndex}
      onKeyDown={
        onClick
          ? (e: React.KeyboardEvent<HTMLDivElement>) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick(e as unknown as React.MouseEvent<HTMLDivElement>);
              }
            }
          : props.onKeyDown
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
