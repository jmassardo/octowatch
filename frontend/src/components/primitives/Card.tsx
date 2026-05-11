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
  headingLevel?: 2 | 3 | 4 | 5 | 6;
}

export function CardHeader({ children, actions, headingLevel = 2 }: CardHeaderProps) {
  const Heading = `h${headingLevel}` as const;

  return (
    <div className={styles.header}>
      <Heading className={styles.headerTitle}>{children}</Heading>
      {actions && <div className={styles.headerActions}>{actions}</div>}
    </div>
  );
}
