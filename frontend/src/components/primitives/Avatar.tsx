import styles from './Avatar.module.css';

function hashColor(str: string): string {
  const colors = [
    '#1f6feb',
    '#238636',
    '#8b5cf6',
    '#db6d28',
    '#bc8cff',
    '#0969da',
    '#bf8700',
    '#cf222e',
  ];
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length] ?? '#1f6feb';
}

function initials(username: string): string {
  const parts = username.replace(/^@/, '').split(/[-_\s]/);
  if (parts.length >= 2) {
    return (parts[0]![0]! + parts[1]![0]!).toUpperCase();
  }
  return username.slice(0, 2).toUpperCase();
}

interface AvatarProps {
  username: string;
  size?: number;
  className?: string;
}

export function Avatar({ username, size = 36, className }: AvatarProps) {
  const bg = hashColor(username);
  const text = initials(username);
  return (
    <div
      className={[styles.avatar, className].filter(Boolean).join(' ')}
      style={{ width: size, height: size, background: bg, fontSize: size * 0.38 }}
    >
      {text}
    </div>
  );
}
