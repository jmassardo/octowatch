import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { AuthGuard } from './components/auth/AuthGuard';
import { LoginPage } from './pages/LoginPage';
import { SetupPage } from './pages/Setup';
import { DashboardPage } from './pages/Dashboard';
import { ThreatsPage } from './pages/Threats';
import { EventsPage } from './pages/Events';
import { VelocityPage } from './pages/Velocity';
import { DevActivityPage } from './pages/DevActivity';
import { CopilotPage } from './pages/Copilot';
import { ReportsPage } from './pages/Reports';
import { QueryPage } from './pages/Query';
import { RulesPage } from './pages/Rules';
import { UsersPage } from './pages/Users';
import { HealthPage } from './pages/Health';
import { HealthSettingsPage } from './pages/Health/HealthSettings';
import { PosturePage } from './pages/Posture';
import { SettingsPage } from './pages/Settings';
import { ActorsPage } from './pages/Actors';

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/dashboard" replace /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/setup', element: <SetupPage /> },
  {
    element: (
      <AuthGuard>
        <AppShell />
      </AuthGuard>
    ),
    errorElement: (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <h2>Page Error</h2>
        <p>
          This page encountered an error. <a href="/dashboard">Return to Dashboard</a>
        </p>
      </div>
    ),
    children: [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/threats', element: <ThreatsPage /> },
      { path: '/actors/:login', element: <ActorsPage /> },
      { path: '/posture', element: <PosturePage /> },
      { path: '/posture/:org', element: <PosturePage /> },
      { path: '/posture/:org/:repo', element: <PosturePage /> },
      { path: '/events', element: <EventsPage /> },
      { path: '/velocity', element: <VelocityPage /> },
      { path: '/devactivity', element: <DevActivityPage /> },
      { path: '/copilot', element: <Navigate to="/copilot/overview" replace /> },
      { path: '/copilot/:tab', element: <CopilotPage /> },
      { path: '/health', element: <Navigate to="/health/repos" replace /> },
      { path: '/health/settings', element: <HealthSettingsPage /> },
      { path: '/health/:tab', element: <HealthPage /> },
      { path: '/reports', element: <ReportsPage /> },
      { path: '/query', element: <QueryPage /> },
      { path: '/rules', element: <RulesPage /> },
      { path: '/users', element: <UsersPage /> },
      { path: '/integrations', element: <Navigate to="/settings/integrations" replace /> },
      { path: '/settings', element: <Navigate to="/settings/all" replace /> },
      { path: '/settings/:tab', element: <SettingsPage /> },
    ],
  },
]);
