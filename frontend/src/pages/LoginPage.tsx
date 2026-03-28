import styles from './LoginPage.module.css';

export function LoginPage() {
  return (
    <div className={styles.page}>
      <div className={styles.box}>
        <div className={styles.logo}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="3.5" fill="#bc8cff" />
            <ellipse cx="12" cy="12" rx="9" ry="5.5" stroke="#bc8cff" strokeWidth="1.5" fill="none" />
            <line x1="12" y1="2" x2="12" y2="5" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="12" y1="19" x2="12" y2="22" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="2" y1="12" x2="5" y2="12" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="19" y1="12" x2="22" y2="12" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>
        <h1 className={styles.title}>OctoWatch</h1>
        <p className={styles.sub}>GitHub Audit Log Security & Intelligence Platform</p>

        <a href="/api/v1/auth/github/login" className={styles.githubBtn}>
          <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
          Sign in with GitHub
        </a>

        <div className={styles.divider}>or</div>

        <a href="/api/v1/auth/saml/login" className={styles.samlBtn}>
          Sign in with SAML SSO
        </a>

        <p className={styles.footer}>
          By signing in, you authorize OctoWatch to access your organization's audit log data.
        </p>
      </div>
    </div>
  );
}
