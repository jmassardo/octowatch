import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import styles from './AppShell.module.css';

export function AppShell() {
  return (
    <div className={styles.layout}>
      <a href="#main-content" className={styles.skipNav}>Skip to main content</a>
      <aside>
        <Sidebar />
      </aside>
      <div className={styles.main}>
        <TopBar />
        <main id="main-content" className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
