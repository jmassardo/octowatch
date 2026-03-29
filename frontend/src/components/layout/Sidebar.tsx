import { NavLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listDetections } from '../../api/detections';
import { getHealthSummary } from '../../api/healthSignals';
import { useFeatures } from '../../hooks/useFeatures';
import styles from './Sidebar.module.css';

function NavItem({
  to,
  icon,
  children,
  badge,
}: {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [styles.navItem, isActive && styles.active].filter(Boolean).join(' ')
      }
    >
      {icon}
      <span>{children}</span>
      {badge !== undefined && badge > 0 && (
        <span className={styles.navCount}>{badge}</span>
      )}
    </NavLink>
  );
}

export function Sidebar() {
  const { features } = useFeatures();

  const { data: detections } = useQuery({
    queryKey: ['threats', 'open-count'],
    queryFn: () => listDetections({ status: 'investigating', page_size: 1 }),
    staleTime: 60_000,
  });

  const threatCount = detections?.total ?? 0;

  const { data: healthSummary } = useQuery({
    queryKey: ['health-signals', 'summary'],
    queryFn: getHealthSummary,
    staleTime: 60_000,
  });

  const healthBadge = healthSummary
    ? healthSummary.stale_repos +
      healthSummary.pat_no_expiry +
      healthSummary.pat_stale +
      healthSummary.bypass_offenders +
      healthSummary.ext_collab_elevated
    : 0;

  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <div className={styles.logo}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
          <circle cx="12" cy="12" r="3.5" fill="#bc8cff" />
          <ellipse cx="12" cy="12" rx="9" ry="5.5" stroke="#bc8cff" strokeWidth="1.5" fill="none" />
          <line x1="12" y1="2" x2="12" y2="5" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="12" y1="19" x2="12" y2="22" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="2" y1="12" x2="5" y2="12" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="19" y1="12" x2="22" y2="12" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        OctoWatch
      </div>

      <div className={styles.navSection}>
        <NavItem
          to="/dashboard"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M1 1.75A.75.75 0 011.75 1h12.5a.75.75 0 010 1.5H1.75A.75.75 0 011 1.75zm0 5A.75.75 0 011.75 6h12.5a.75.75 0 010 1.5H1.75A.75.75 0 011 6.75zm0 5a.75.75 0 01.75-.75h12.5a.75.75 0 010 1.5H1.75a.75.75 0 01-.75-.75z" />
            </svg>
          }
        >
          Dashboard
        </NavItem>
      </div>

      <div className={styles.navSection}>
        <div className={styles.navLabel}>Security</div>
        <NavItem
          to="/threats"
          badge={threatCount}
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M7.467.133a1.748 1.748 0 011.066 0l5.25 1.68A1.75 1.75 0 0115 3.48V7c0 1.566-.32 3.182-1.303 4.682-.983 1.498-2.585 2.813-5.032 3.855a1.697 1.697 0 01-1.33 0c-2.447-1.042-4.049-2.357-5.032-3.855C1.32 10.182 1 8.566 1 7V3.48a1.75 1.75 0 011.217-1.667z" />
            </svg>
          }
        >
          Threat Detections
        </NavItem>
        <NavItem
          to="/events"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M2 2.75C2 1.784 2.784 1 3.75 1h8.5c.966 0 1.75.784 1.75 1.75v11.5A1.75 1.75 0 0112.25 16h-8.5A1.75 1.75 0 012 14.25zm1.75-.25a.25.25 0 00-.25.25v11.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V2.75a.25.25 0 00-.25-.25z" />
            </svg>
          }
        >
          Events Explorer
        </NavItem>
      </div>

      <div className={styles.navSection}>
        <div className={styles.navLabel}>Platform Intelligence</div>
        {features.velocity && (
        <NavItem
          to="/velocity"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M8.75 1.75a.75.75 0 00-1.5 0v5.268L5.78 5.543a.75.75 0 10-1.06 1.06l2.72 2.72.707-.707-.707.707a.75.75 0 001.06 0l2.72-2.72a.75.75 0 10-1.06-1.06L8.75 7.018z" />
              <path d="M2 8a6 6 0 1012 0A6 6 0 002 8zm-.5 0a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z" />
            </svg>
          }
        >
          Engineering Velocity
        </NavItem>
        )}
        {features.dev_activity && (
        <NavItem
          to="/devactivity"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M10.5 5a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm.061 3.073a4 4 0 10-5.123 0 6.004 6.004 0 00-3.431 5.142.75.75 0 001.498.07 4.5 4.5 0 018.99 0 .75.75 0 101.498-.07 6.005 6.005 0 00-3.432-5.142z" />
            </svg>
          }
        >
          Developer Activity
        </NavItem>
        )}
        {features.copilot_insights && (
        <NavItem
          to="/copilot"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M0 1.75A.75.75 0 01.75 1h4.253c1.227 0 2.317.59 3 1.5A3.744 3.744 0 0111.006 1h4.245a.75.75 0 01.75.75v10.5a.75.75 0 01-.75.75h-4.507a2.25 2.25 0 00-1.591.659l-.622.621a.75.75 0 01-1.06 0l-.622-.621A2.25 2.25 0 005.258 13H.75a.75.75 0 01-.75-.75zm8.5 9.5a3.75 3.75 0 013-3.75V4.75A2.25 2.25 0 009.253 2.5H7.5A.25.25 0 007.25 2.75v8.29a4.74 4.74 0 011.25-.79zm-1 0a4.74 4.74 0 011.25.79V2.75A.25.25 0 008.5 2.5H6.747A2.25 2.25 0 004.5 4.75v2.25A3.75 3.75 0 017.5 10.75z" />
            </svg>
          }
        >
          Copilot Insights
        </NavItem>
        )}
        {features.org_health && (
        <NavItem
          to="/health"
          badge={healthBadge}
          icon={
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M7.467.133a1.75 1.75 0 011.066 0l5.25 1.68A1.75 1.75 0 0115 3.48V7c0 1.566-.32 3.182-1.303 4.682-.983 1.498-2.585 2.813-5.032 3.855a1.697 1.697 0 01-1.33 0C4.888 14.495 3.286 13.18 2.303 11.682 1.32 10.182 1 8.566 1 7V3.48a1.75 1.75 0 011.217-1.667l5.25-1.68zm.61 1.429a.25.25 0 00-.153 0l-5.25 1.68a.25.25 0 00-.174.238V7c0 1.358.275 2.666 1.057 3.86.784 1.194 2.121 2.34 4.366 3.297a.196.196 0 00.154 0c2.245-.956 3.582-2.104 4.366-3.298C13.225 9.666 13.5 8.36 13.5 7V3.48a.25.25 0 00-.174-.238l-5.25-1.68z" />
            </svg>
          }
        >
          Org Health
        </NavItem>
        )}
      </div>

      <div className={styles.navSection}>
        <div className={styles.navLabel}>Analytics</div>
        <NavItem
          to="/reports"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0114.25 13H8.06l-2.573 2.573A1.458 1.458 0 013 14.543V13H1.75A1.75 1.75 0 010 11.25z" />
            </svg>
          }
        >
          Reports
        </NavItem>
        <NavItem
          to="/query"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M10.68 11.74a6 6 0 01-7.922-8.982 6 6 0 018.982 7.922l3.04 3.04a.749.749 0 11-1.06 1.06zm-3.18.26a4.5 4.5 0 100-9 4.5 4.5 0 000 9z" />
            </svg>
          }
        >
          Query Explorer
        </NavItem>
      </div>

      <div className={styles.navSection}>
        <div className={styles.navLabel}>Settings</div>
        <NavItem
          to="/rules"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M3.72 3.72a.75.75 0 011.06 1.06L2.56 7h10.88l-2.22-2.22a.75.75 0 011.06-1.06l3.5 3.5a.75.75 0 010 1.06l-3.5 3.5a.75.75 0 11-1.06-1.06L13.44 9H2.56l2.22 2.22a.75.75 0 11-1.06 1.06l-3.5-3.5a.75.75 0 010-1.06z" />
            </svg>
          }
        >
          Detection Rules
        </NavItem>
        <NavItem
          to="/users"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M10.5 5a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm4.5 12.25a.75.75 0 01-.75.75H1.75a.75.75 0 010-1.5A6.25 6.25 0 0114.25 12.5a.75.75 0 01.75.75z" />
            </svg>
          }
        >
          Users & Roles
        </NavItem>
        <NavItem
          to="/integrations"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5z" />
            </svg>
          }
        >
          Integrations
        </NavItem>
        <NavItem
          to="/settings"
          icon={
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M8 0a8.2 8.2 0 01.701.031C9.444.095 9.99.645 10.16 1.29l.035.133a1.244 1.244 0 001.578.741l.124-.042c.63-.214 1.336-.065 1.77.49l.1.136.064.09a8.18 8.18 0 01.686 1.188l.06.136c.284.645.065 1.39-.5 1.825l-.107.077a1.244 1.244 0 000 1.71l.107.078c.565.434.784 1.18.5 1.825l-.06.135a8.2 8.2 0 01-.687 1.19l-.063.089-.101.136c-.434.555-1.14.704-1.77.49l-.124-.042a1.244 1.244 0 00-1.578.74l-.035.134c-.17.645-.716 1.195-1.459 1.26a8.3 8.3 0 01-1.402 0c-.743-.065-1.289-.615-1.459-1.26l-.035-.134a1.244 1.244 0 00-1.578-.74l-.124.041c-.63.215-1.336.066-1.77-.49l-.101-.135-.063-.09a8.2 8.2 0 01-.687-1.189l-.06-.135c-.284-.646-.065-1.392.5-1.826l.107-.077a1.244 1.244 0 000-1.711l-.107-.077c-.565-.434-.784-1.18-.5-1.825l.06-.136a8.2 8.2 0 01.687-1.188l.063-.09.101-.136c.434-.555 1.14-.704 1.77-.49l.124.042a1.244 1.244 0 001.578-.741l.035-.133C6.01.645 6.556.095 7.299.03 7.53.01 7.764 0 8 0zM6.92 1.49l-.038.148a2.744 2.744 0 01-3.48 1.634l-.136-.046a6.7 6.7 0 00-.455.79l.118.086a2.744 2.744 0 010 3.774l-.118.085c.12.274.268.539.455.791l.136-.046a2.744 2.744 0 013.48 1.634l.038.148c.307.013.617.013.924 0l-.001-.001.04-.148a2.744 2.744 0 013.48-1.633l.136.046c.187-.253.336-.517.455-.79l-.118-.087a2.744 2.744 0 010-3.773l.118-.086a6.7 6.7 0 00-.455-.79l-.136.046a2.744 2.744 0 01-3.48-1.634l-.04-.149a7 7 0 00-.923 0zM8 5.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5zM7 8a1 1 0 112 0 1 1 0 01-2 0z" />
            </svg>
          }
        >
          Settings
        </NavItem>
      </div>
    </nav>
  );
}
