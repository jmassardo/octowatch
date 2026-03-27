import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useOrg } from '../../hooks/useOrg';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useTheme } from '../../hooks/useTheme';
import { Avatar } from '../primitives/Avatar';
import { Button } from '../primitives/Button';
import { logout } from '../../api/auth';
import styles from './TopBar.module.css';

export function TopBar() {
  const { selectedOrg, setSelectedOrg } = useOrg();
  const { data: user } = useCurrentUser();
  const queryClient = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const avatarRef = useRef<HTMLButtonElement>(null);
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [filterText, setFilterText] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const filterInputRef = useRef<HTMLInputElement>(null);

  const orgs: readonly string[] = user?.scoped_orgs ?? [];

  const filteredOrgs = orgs.filter((org) =>
    org.toLowerCase().includes(filterText.toLowerCase()),
  );

  const handleClickOutside = useCallback(
    (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
        setFilterText('');
      }
    },
    [],
  );

  useEffect(() => {
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      filterInputRef.current?.focus();
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen, handleClickOutside]);

  function selectOrg(org: string) {
    setSelectedOrg(org);
    setDropdownOpen(false);
    setFilterText('');
  }

  const themeIcon = theme === 'light' ? '☀️' : theme === 'dark' ? '🌙' : '💻';
  const themeLabel = theme === 'light' ? 'Light' : theme === 'dark' ? 'Dark' : 'System';

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // best-effort — clear state regardless
    }
    queryClient.clear();
    window.location.replace('/login');
  }

  return (
    <header className={styles.topbar} role="banner">
      <div className={styles.orgDropdownWrap} ref={dropdownRef}>
        <button
          className={styles.orgDropdownTrigger}
          onClick={() => setDropdownOpen((prev) => !prev)}
          aria-expanded={dropdownOpen}
          aria-haspopup="listbox"
          aria-label="Select organization"
        >
          <span className={styles.orgDropdownLabel}>
            {selectedOrg || 'All organizations'}
          </span>
          <span className={styles.orgDropdownChevron} aria-hidden="true">
            ▾
          </span>
        </button>

        {dropdownOpen && (
          <div
            className={styles.orgDropdownPanel}
            role="listbox"
            aria-label="Organizations"
          >
            <input
              ref={filterInputRef}
              className={styles.orgDropdownFilter}
              type="text"
              placeholder="Filter organizations..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              aria-label="Filter organizations"
            />
            <div className={styles.orgDropdownList}>
              <button
                className={`${styles.orgDropdownItem}${selectedOrg === '' ? ` ${styles.orgDropdownItemSelected}` : ''}`}
                role="option"
                aria-selected={selectedOrg === ''}
                onClick={() => selectOrg('')}
              >
                All organizations
                {selectedOrg === '' && (
                  <span className={styles.orgDropdownCheck} aria-hidden="true">
                    ✓
                  </span>
                )}
              </button>

              {orgs.length === 0 ? (
                <div
                  className={styles.orgDropdownEmpty}
                  role="option"
                  aria-disabled="true"
                >
                  No organizations
                </div>
              ) : (
                filteredOrgs.map((org) => (
                  <button
                    key={org}
                    className={`${styles.orgDropdownItem}${org === selectedOrg ? ` ${styles.orgDropdownItemSelected}` : ''}`}
                    role="option"
                    aria-selected={org === selectedOrg}
                    onClick={() => selectOrg(org)}
                  >
                    {org}
                    {org === selectedOrg && (
                      <span
                        className={styles.orgDropdownCheck}
                        aria-hidden="true"
                      >
                        ✓
                      </span>
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      <div className={styles.right}>
        <button
          className={styles.themeToggle}
          onClick={toggleTheme}
          aria-label={`Theme: ${themeLabel}. Click to toggle.`}
          title={`Theme: ${themeLabel}`}
        >
          {themeIcon}
        </button>
        <Button size="sm" onClick={() => navigate('/reports')}>
          <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
            <path d="M8 2a.75.75 0 01.75.75v4.5h4.5a.75.75 0 010 1.5h-4.5v4.5a.75.75 0 01-1.5 0v-4.5h-4.5a.75.75 0 010-1.5h4.5v-4.5A.75.75 0 018 2z" />
          </svg>
          New report
        </Button>
        {user && (
          <div className={styles.avatarWrap}>
            <button
              ref={avatarRef}
              className={styles.avatarBtn}
              onClick={() => setMenuOpen((o) => !o)}
              aria-label="User menu"
              aria-expanded={menuOpen}
            >
              <Avatar username={user.github_login} size={28} />
            </button>
            {menuOpen && (
              <>
                <div className={styles.menuBackdrop} onClick={() => setMenuOpen(false)} />
                <div className={styles.menu}>
                  <div className={styles.menuHeader}>
                    <span className={styles.menuLogin}>@{user.github_login}</span>
                    {user.roles.length > 0 && (
                      <span className={styles.menuRole}>{user.roles[0]}</span>
                    )}
                  </div>
                  <div className={styles.menuDivider} />
                  <button className={styles.menuItem} onClick={handleLogout}>
                    <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                      <path d="M2 2.75C2 1.784 2.784 1 3.75 1h4.5a.75.75 0 010 1.5h-4.5a.25.25 0 00-.25.25v10.5c0 .138.112.25.25.25h4.5a.75.75 0 010 1.5h-4.5A1.75 1.75 0 012 13.25V2.75zm9.47 4L9.22 4.5a.75.75 0 011.06-1.06l3.25 3.25a.75.75 0 010 1.06l-3.25 3.25a.75.75 0 01-1.06-1.06l2.25-2.25H6.75a.75.75 0 010-1.5h4.72z" />
                    </svg>
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
