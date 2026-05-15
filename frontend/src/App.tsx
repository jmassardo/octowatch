import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { AuthGuard } from './components/auth/AuthGuard';
import { LoginPage } from './pages/LoginPage';
import { SetupPage } from './pages/Setup';
import { DashboardPage } from './pages/Dashboard';
import { ThreatsPage } from './pages/Threats';
import { EventsPage } from './pages/Events';
import { EventDetailPage } from './pages/Events/EventDetailPage';
import { VelocityPage } from './pages/Velocity';
import { DevActivityPage } from './pages/DevActivity';
import { CopilotPage } from './pages/Copilot';
import { ReportsPage } from './pages/Reports';
import { CompliancePage } from './pages/Compliance';
import { QueryPage } from './pages/Query';
import { RulesPage } from './pages/Rules';
import { UsersPage } from './pages/Users';
import { HealthPage } from './pages/Health';
import { HealthSettingsPage } from './pages/Health/HealthSettings';
import { PosturePage } from './pages/Posture';
import { SettingsPage } from './pages/Settings';
import { TelemetryPage } from './pages/Telemetry';
import { ActorsPage } from './pages/Actors';
import { CrossOrgPage } from './pages/CrossOrg';
import { WorkflowsPage } from './pages/Workflows';
import { WorkflowHealthPage } from './pages/WorkflowHealth';
import { AdvancedSecurityPage } from './pages/AdvancedSecurity';
import { PlaybooksPage } from './pages/Playbooks';
import { SupplyChainPage } from './pages/SupplyChain';
import { ThreatIntelPage } from './pages/ThreatIntel';
import { SyncStatusPage } from './pages/SyncStatus';
import { NotificationsPage } from './pages/Notifications';
import AuthSettingsPage from './pages/admin/AuthSettings';
import { ProfilePage } from './pages/Profile';
import { CustomDashboardPage } from './pages/CustomDashboard';

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
      { path: '/dashboard/custom', element: <CustomDashboardPage /> },
      { path: '/threats', element: <ThreatsPage /> },
      { path: '/threat-intel', element: <ThreatIntelPage /> },
      { path: '/actors/:login', element: <ActorsPage /> },
      { path: '/posture', element: <PosturePage /> },
      { path: '/posture/:org', element: <PosturePage /> },
      { path: '/posture/:org/:repo', element: <PosturePage /> },
      { path: '/events', element: <EventsPage /> },
      { path: '/events/:id', element: <EventDetailPage /> },
      { path: '/crossorg', element: <CrossOrgPage /> },
      { path: '/workflows', element: <WorkflowsPage /> },
      { path: '/workflows/health', element: <WorkflowHealthPage /> },
      { path: '/advanced-security', element: <AdvancedSecurityPage /> },
      { path: '/supply-chain', element: <SupplyChainPage /> },
      { path: '/playbooks', element: <PlaybooksPage /> },
      { path: '/velocity', element: <VelocityPage /> },
      { path: '/devactivity', element: <DevActivityPage /> },
      { path: '/copilot', element: <Navigate to="/copilot/overview" replace /> },
      { path: '/copilot/:tab', element: <CopilotPage /> },
      { path: '/health', element: <Navigate to="/health/repos" replace /> },
      { path: '/health/settings', element: <HealthSettingsPage /> },
      { path: '/health/:tab', element: <HealthPage /> },
      { path: '/reports', element: <ReportsPage /> },
      { path: '/compliance', element: <CompliancePage /> },
      { path: '/query', element: <QueryPage /> },
      { path: '/rules', element: <RulesPage /> },
      { path: '/users', element: <UsersPage /> },
      { path: '/notifications', element: <NotificationsPage /> },
      { path: '/integrations', element: <Navigate to="/settings/integrations" replace /> },
      { path: '/settings', element: <Navigate to="/settings/all" replace /> },
      { path: '/settings/:tab', element: <SettingsPage /> },
      { path: '/telemetry', element: <TelemetryPage /> },
      { path: '/monitoring/sync-status', element: <SyncStatusPage /> },
      { path: '/admin/auth', element: <AuthSettingsPage /> },
      { path: '/profile', element: <ProfilePage /> },
    ],
  },
]);
