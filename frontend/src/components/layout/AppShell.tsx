import { useState, useCallback, useMemo } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { GuidedTour } from '../GuidedTour/GuidedTour';
import { isTourCompleted, resetTour } from '../GuidedTour/tourStorage';
import { HotkeyProvider } from '../../contexts/HotkeyProvider';
import { useHotkeys, type HotkeyBinding } from '../../hooks/useHotkeys';
import { ShortcutsDialog } from '../common/ShortcutsDialog';
import styles from './AppShell.module.css';

function AppShellInner() {
  const [showTour, setShowTour] = useState(!isTourCompleted());
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const navigate = useNavigate();

  function handleReplayTour() {
    resetTour();
    setShowTour(true);
  }

  const openShortcuts = useCallback(() => setShortcutsOpen(true), []);
  const closeShortcuts = useCallback(() => setShortcutsOpen(false), []);

  const focusSearchInput = useCallback(() => {
    const input = document.querySelector<HTMLInputElement>(
      'input[type="search"], input[placeholder*="earch"], input[placeholder*="ilter"], input[aria-label*="earch"], input[aria-label*="ilter"]',
    );
    if (input) {
      input.focus();
      input.select();
    }
  }, []);

  const bindings: HotkeyBinding[] = useMemo(
    () => [
      /* ── Navigation: g then <key> ─────────────────────────────── */
      {
        key: 'g d',
        handler: () => navigate('/dashboard'),
        label: 'Go to Dashboard',
        category: 'Navigation',
      },
      {
        key: 'g t',
        handler: () => navigate('/threats'),
        label: 'Go to Threats',
        category: 'Navigation',
      },
      {
        key: 'g e',
        handler: () => navigate('/events'),
        label: 'Go to Events',
        category: 'Navigation',
      },
      {
        key: 'g p',
        handler: () => navigate('/posture'),
        label: 'Go to Posture',
        category: 'Navigation',
      },
      {
        key: 'g w',
        handler: () => navigate('/workflows'),
        label: 'Go to Workflows',
        category: 'Navigation',
      },
      {
        key: 'g c',
        handler: () => navigate('/copilot'),
        label: 'Go to Copilot',
        category: 'Navigation',
      },
      {
        key: 'g v',
        handler: () => navigate('/velocity'),
        label: 'Go to Velocity',
        category: 'Navigation',
      },
      {
        key: 'g r',
        handler: () => navigate('/reports'),
        label: 'Go to Reports',
        category: 'Navigation',
      },
      {
        key: 'g s',
        handler: () => navigate('/settings'),
        label: 'Go to Settings',
        category: 'Navigation',
      },

      /* ── Actions ──────────────────────────────────────────────── */
      { key: 'f', handler: focusSearchInput, label: 'Focus search / filter', category: 'Actions' },

      /* ── General ──────────────────────────────────────────────── */
      { key: '?', handler: openShortcuts, label: 'Show keyboard shortcuts', category: 'General' },
    ],
    [navigate, openShortcuts, focusSearchInput],
  );

  useHotkeys(bindings);

  return (
    <div className={styles.layout}>
      <a href="#main-content" className={styles.skipNav}>
        Skip to main content
      </a>
      <aside className={styles.desktopSidebar}>
        <Sidebar />
      </aside>
      <aside className={styles.mobileSidebar}>
        <Sidebar mobileOpen={sidebarOpen} onMobileClose={() => setSidebarOpen(false)} />
      </aside>
      <div className={styles.main}>
        <TopBar onShowTour={handleReplayTour} onToggleSidebar={() => setSidebarOpen((o) => !o)} />
        <main id="main-content" className={styles.content}>
          <Outlet />
        </main>
      </div>
      {showTour && <GuidedTour onComplete={() => setShowTour(false)} />}
      <ShortcutsDialog open={shortcutsOpen} onClose={closeShortcuts} />
    </div>
  );
}

export function AppShell() {
  return (
    <HotkeyProvider>
      <AppShellInner />
    </HotkeyProvider>
  );
}
