import { useOrg } from '../../hooks/useOrg';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { Avatar } from '../primitives/Avatar';
import { Button } from '../primitives/Button';
import styles from './TopBar.module.css';

export function TopBar() {
  const { selectedOrg, setSelectedOrg } = useOrg();
  const { data: user } = useCurrentUser();

  const orgs = user?.scoped_orgs ?? [];

  return (
    <div className={styles.topbar}>
      <div className={styles.orgTabs}>
        {orgs.map((org) => (
          <button
            key={org}
            className={[styles.orgTab, org === selectedOrg && styles.active].filter(Boolean).join(' ')}
            onClick={() => setSelectedOrg(org)}
          >
            {org}
          </button>
        ))}
        {orgs.length === 0 && (
          <button className={[styles.orgTab, styles.active].filter(Boolean).join(' ')}>
            All orgs
          </button>
        )}
      </div>
      <div className={styles.right}>
        <Button size="sm">
          <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
            <path d="M8 2a.75.75 0 01.75.75v4.5h4.5a.75.75 0 010 1.5h-4.5v4.5a.75.75 0 01-1.5 0v-4.5h-4.5a.75.75 0 010-1.5h4.5v-4.5A.75.75 0 018 2z" />
          </svg>
          New report
        </Button>
        {user && (
          <Avatar username={user.github_login} size={28} />
        )}
      </div>
    </div>
  );
}
