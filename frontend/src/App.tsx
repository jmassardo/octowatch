import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { AuthGuard } from './components/auth/AuthGuard';
import { LegacyTabRedirect } from './components/common/LegacyTabRedirect';
import { RedirectAfterLogin } from './components/auth/RedirectAfterLogin';
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
import { PlatformUsagePage } from './pages/PlatformUsage';
import { AuditTrailPage } from './pages/AuditTrail';
import { ActorsPage } from './pages/Actors';
import { CrossOrgPage } from './pages/CrossOrg';
import { WorkflowsPage } from './pages/Workflows';
import { WorkflowHealthPage } from './pages/WorkflowHealth';
import { AdvancedSecurityPage } from './pages/AdvancedSecurity';
import { PlaybooksPage } from './pages/Playbooks';
import { SupplyChainPage } from './pages/SupplyChain';
import { PackagesPage } from './pages/Packages';
import { UserBehaviorPage } from './pages/UserBehavior';
import { ThreatIntelPage } from './pages/ThreatIntel';
import { ThreatIntelFeedDetailPage } from './pages/ThreatIntel/FeedDetailPage';
import { SyncStatusPage } from './pages/SyncStatus';
import { NotificationsPage } from './pages/Notifications';
import AuthSettingsPage from './pages/admin/AuthSettings';
import { ProfilePage } from './pages/Profile';

export const router = createBrowserRouter(
  [
    { path: '/', element: <RedirectAfterLogin /> },
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
        { path: '/dashboard/custom', element: <Navigate to="/dashboard?view=widgets" replace /> },
        { path: '/threats', element: <Navigate to="/threats/open" replace /> },
        { path: '/threats/:tab', element: <ThreatsPage /> },
        {
          path: '/threat-intel',
          element: (
            <LegacyTabRedirect
              basePath="/threat-intel"
              validTabs={['feeds', 'indicators', 'matches', 'analytics']}
              defaultTab="feeds"
            />
          ),
        },
        {
          path: '/workflows',
          element: (
            <LegacyTabRedirect
              basePath="/workflows"
              validTabs={['findings', 'scores', 'activity', 'rules']}
              defaultTab="findings"
            />
          ),
        },
        { path: '/workflows/health', element: <WorkflowHealthPage /> },
        { path: '/workflows/:tab', element: <WorkflowsPage /> },
        { path: '/threat-intel/:tab', element: <ThreatIntelPage /> },
        { path: '/threat-intel/feeds/:feedId', element: <ThreatIntelFeedDetailPage /> },
        { path: '/actors/:login', element: <ActorsPage /> },
        { path: '/posture', element: <PosturePage /> },
        { path: '/posture/:org', element: <PosturePage /> },
        { path: '/posture/:org/:repo', element: <PosturePage /> },
        { path: '/events', element: <EventsPage /> },
        { path: '/events/:id', element: <EventDetailPage /> },
        { path: '/crossorg', element: <CrossOrgPage /> },
        {
          path: '/advanced-security',
          element: <Navigate to="/advanced-security/overview" replace />,
        },
        { path: '/advanced-security/:tab', element: <AdvancedSecurityPage /> },
        {
          path: '/supply-chain',
          element: (
            <LegacyTabRedirect
              basePath="/supply-chain"
              validTabs={['risks', 'rules', 'workflow']}
              defaultTab="risks"
            />
          ),
        },
        { path: '/supply-chain/:tab', element: <SupplyChainPage /> },
        {
          path: '/packages',
          element: (
            <LegacyTabRedirect
              basePath="/packages"
              validTabs={['overview', 'inventory', 'alerts', 'container-health']}
              defaultTab="overview"
            />
          ),
        },
        { path: '/packages/:tab', element: <PackagesPage /> },
        { path: '/playbooks', element: <PlaybooksPage /> },
        { path: '/velocity', element: <VelocityPage /> },
        { path: '/devactivity', element: <DevActivityPage /> },
        {
          path: '/user-behavior',
          element: (
            <LegacyTabRedirect
              basePath="/user-behavior"
              validTabs={['risky-users', 'anomalies', 'permissions']}
              defaultTab="risky-users"
            />
          ),
        },
        { path: '/user-behavior/:tab', element: <UserBehaviorPage /> },
        { path: '/copilot', element: <Navigate to="/copilot/overview" replace /> },
        { path: '/copilot/:tab', element: <CopilotPage /> },
        { path: '/health', element: <Navigate to="/health/repos" replace /> },
        { path: '/health/settings', element: <HealthSettingsPage /> },
        { path: '/health/:tab', element: <HealthPage /> },
        {
          path: '/reports',
          element: (
            <LegacyTabRedirect
              basePath="/reports"
              validTabs={['templates', 'my-reports', 'shared', 'recent']}
              defaultTab="templates"
            />
          ),
        },
        { path: '/reports/:tab', element: <ReportsPage /> },
        {
          path: '/compliance',
          element: (
            <LegacyTabRedirect
              basePath="/compliance"
              validTabs={['overview', 'soc2', 'iso27001', 'nist_csf', 'gdpr', 'policy']}
              defaultTab="overview"
            />
          ),
        },
        { path: '/compliance/:tab', element: <CompliancePage /> },
        { path: '/query', element: <QueryPage /> },
        { path: '/rules', element: <RulesPage /> },
        { path: '/rules/:ruleId', element: <RulesPage /> },
        {
          path: '/users',
          element: (
            <LegacyTabRedirect
              basePath="/users"
              validTabs={['users', 'roles']}
              defaultTab="users"
            />
          ),
        },
        { path: '/users/:tab', element: <UsersPage /> },
        {
          path: '/notifications',
          element: <Navigate to="/notifications/alerts" replace />,
        },
        { path: '/notifications/:tab', element: <NotificationsPage /> },
        { path: '/integrations', element: <Navigate to="/settings/integrations" replace /> },
        { path: '/settings', element: <Navigate to="/settings/all" replace /> },
        { path: '/settings/:tab', element: <SettingsPage /> },
        {
          path: '/monitoring/telemetry',
          element: (
            <LegacyTabRedirect
              basePath="/monitoring/telemetry"
              validTabs={['streams', 'workers', 'volume', 'errors']}
              defaultTab="streams"
            />
          ),
        },
        { path: '/monitoring/telemetry/:tab', element: <TelemetryPage /> },
        { path: '/monitoring/platform-usage', element: <PlatformUsagePage /> },
        { path: '/monitoring/audit-trail', element: <AuditTrailPage /> },
        { path: '/telemetry', element: <Navigate to="/monitoring/telemetry" replace /> },
        { path: '/monitoring/sync-status', element: <SyncStatusPage /> },
        { path: '/admin/auth', element: <AuthSettingsPage /> },
        { path: '/profile', element: <Navigate to="/profile/preferences" replace /> },
        { path: '/profile/:tab', element: <ProfilePage /> },
      ],
    },
  ],
  {
    future: {
      v7_relativeSplatPath: true,
    },
  },
);
