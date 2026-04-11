import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { GuidedTour } from '../GuidedTour/GuidedTour';
import { isTourCompleted, resetTour } from '../GuidedTour/tourStorage';
import styles from './AppShell.module.css';

export function AppShell() {
  const [showTour, setShowTour] = useState(!isTourCompleted());
  const [sidebarOpen, setSidebarOpen] = useState(false);

  function handleReplayTour() {
    resetTour();
    setShowTour(true);
  }

  return (
    <div className={styles.layout}>
      <a href="#main-content" className={styles.skipNav}>
        Skip to main content
      </a>
      <aside className={styles.desktopSidebar}>
        <Sidebar />
      </aside>
      <aside className={styles.mobileSidebar}>
        <Sidebar
          mobileOpen={sidebarOpen}
          onMobileClose={() => setSidebarOpen(false)}
        />
      </aside>
      <div className={styles.main}>
        <TopBar
          onShowTour={handleReplayTour}
          onToggleSidebar={() => setSidebarOpen((o) => !o)}
        />
        <main id="main-content" className={styles.content}>
          <Outlet />
        </main>
      </div>
      {showTour && <GuidedTour onComplete={() => setShowTour(false)} />}
    </div>
  );
}
