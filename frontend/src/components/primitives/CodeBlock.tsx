import styles from './CodeBlock.module.css';

interface CodeBlockProps {
  children: React.ReactNode;
  className?: string;
}

export function CodeBlock({ children, className }: CodeBlockProps) {
  return (
    <pre className={[styles.block, className].filter(Boolean).join(' ')}>
      <code>{children}</code>
    </pre>
  );
}
