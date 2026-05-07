import type { RuleCategory } from '../../types/detections';

export function getSampleEvent(category: RuleCategory): Record<string, unknown> {
  const base = {
    actor: 'octocat',
    actor_id: 583231,
    org: 'my-org',
    created_at: new Date().toISOString(),
  };

  switch (category) {
    case 'exfiltration':
      return {
        ...base,
        action: 'repo.clone',
        repo: 'my-org/private-repo',
        source_ip: '203.0.113.42',
        data: { transport_protocol_name: 'http', visibility: 'private' },
      };
    case 'account_compromise':
      return {
        ...base,
        action: 'auth.login',
        source_ip: '198.51.100.1',
        data: { auth_method: 'password' },
      };
    case 'privilege_escalation':
      return {
        ...base,
        action: 'org.update_member',
        repo: 'my-org/admin-repo',
        data: { permission: 'admin', old_permission: 'read' },
      };
    case 'secret_leakage':
      return {
        ...base,
        action: 'git.push',
        repo: 'my-org/app-repo',
        data: { alert_type: 'secret_scanning' },
      };
    case 'supply_chain':
      return {
        ...base,
        action: 'packages.package_version_published',
        repo: 'my-org/npm-pkg',
        data: { package_type: 'npm' },
      };
    case 'branch_protection_bypass':
      return {
        ...base,
        action: 'protected_branch.policy_override',
        repo: 'my-org/main-repo',
        data: { branch: 'main' },
      };
    case 'pat_abuse':
      return {
        ...base,
        action: 'personal_access_token.create',
        data: { scopes: 'repo,admin:org' },
      };
    case 'impossible_travel':
      return {
        ...base,
        action: 'auth.login',
        source_ip: '203.0.113.42',
        geo_country_code: 'US',
        geo_latitude: 37.7749,
        geo_longitude: -122.4194,
        data: {},
      };
    case 'off_hours_anomaly':
      return { ...base, action: 'repos.create', repo: 'my-org/new-repo', data: {} };
    default:
      return {
        ...base,
        action: 'repos.create',
        repo: 'my-org/hello-world',
        data: { description: 'A new repository' },
      };
  }
}
