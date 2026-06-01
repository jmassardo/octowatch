import { useState, useCallback, useMemo } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { GuidedTour } from '../GuidedTour/GuidedTour';
import { MaintenanceBanner } from './MaintenanceBanner';
import { CommandPalette } from '../common/CommandPalette';
import { SkipToContent } from '../common/SkipToContent';
import { isTourCompleted, resetTour } from '../GuidedTour/tourStorage';
import { HotkeyProvider } from '../../contexts/HotkeyProvider';
import { useHotkeys, type HotkeyBinding } from '../../hooks/useHotkeys';
import { ShortcutsDialog } from '../common/ShortcutsDialog';
import { useCommandPalette } from '../../hooks/useCommandPalette';
import { useSessionTimeout } from '../../hooks/useSessionTimeout';
import styles from './AppShell.module.css';

function AppShellInner() {
  const [showTour, setShowTour] = useState(!isTourCompleted());
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const navigate = useNavigate();
  const commandPalette = useCommandPalette();

  // Activity-aware session timeout — resets on user interaction and API calls
  useSessionTimeout();

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
      <SkipToContent />
      <aside className={styles.desktopSidebar} aria-label="Primary sidebar">
        <Sidebar />
      </aside>
      <aside className={styles.mobileSidebar} aria-label="Primary sidebar">
        <Sidebar mobileOpen={sidebarOpen} onMobileClose={() => setSidebarOpen(false)} />
      </aside>
      <div className={styles.main}>
        <TopBar
          onShowTour={handleReplayTour}
          onToggleSidebar={() => setSidebarOpen((o) => !o)}
          sidebarOpen={sidebarOpen}
          onOpenSearch={commandPalette.open}
          onOpenShortcuts={openShortcuts}
        />
        <MaintenanceBanner />
        <main id="main-content" className={styles.content} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
      {showTour && <GuidedTour onComplete={() => setShowTour(false)} />}
      <ShortcutsDialog open={shortcutsOpen} onClose={closeShortcuts} />
      {commandPalette.isOpen && (
        <CommandPalette isOpen={commandPalette.isOpen} onClose={commandPalette.close} />
      )}
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
