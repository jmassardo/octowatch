import { useState } from 'react';
import { Avatar } from '../../components/primitives/Avatar';
import { Label } from '../../components/primitives/Label';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { MiniBarChart } from '../../components/charts/MiniBarChart';
import styles from './DevActivity.module.css';

const TEAMS = ['All teams', 'platform-team', 'security-team', 'frontend-team'];

const PR_AUTHORS = [
  { handle: 'alice', pct: 31, color: '#1f6feb' },
  { handle: 'david', pct: 24, color: '#1f6feb' },
  { handle: 'carol', pct: 20, color: '#238636' },
  { handle: 'bob', pct: 16, color: '#238636' },
  { handle: 'eremin', pct: 8, color: '#58a6ff' },
  { handle: 'others (7)', pct: 1, color: '#30363d', muted: true },
];

const REVIEWERS = [
  { handle: 'alice', pct: 44, color: 'var(--danger)', danger: true },
  { handle: 'carol', pct: 28, color: 'var(--attention)', warn: true },
  { handle: 'david', pct: 18, color: '#238636' },
  { handle: 'bob', pct: 10, color: '#238636' },
];

const DEVS = [
  {
    name: 'mal-user99', handle: 'mal-user99', team: 'external', flagged: true,
    bars: [8, 14, 6, 20, 18, 22, 10], barColor: 'var(--danger)',
    repos: 3, prs: 0, detections: 2, flagLabel: 'flagged',
    initials: 'MU', avatarColor: '#8b5cf6',
  },
  {
    name: 'Alice Lund', handle: 'alice', team: 'platform-team',
    bars: [14, 20, 18, 22, 16, 20, 24],
    repos: 12, prs: 47, detections: 0, flagLabel: null,
    initials: 'AL', avatarColor: '#1f6feb',
  },
  {
    name: 'Carol Asuquo', handle: 'carol', team: 'platform-team',
    bars: [20, 16, 22, 18, 24, 14, 20],
    repos: 8, prs: 31, detections: 0, flagLabel: null,
    initials: 'CA', avatarColor: '#238636',
  },
  {
    name: 'Emil Remin', handle: 'eremin', team: 'security-team', reviewed: true,
    bars: [18, 22, 16, 20, 14, 22, 18], barColor: 'var(--attention)',
    repos: 5, prs: 12, detections: 1, flagLabel: 'review',
    initials: 'ER', avatarColor: '#db6d28',
  },
  {
    name: 'Bob Davies', handle: 'bob', team: 'frontend-team',
    bars: [12, 18, 14, 20, 16, 18, 22],
    repos: 6, prs: 24, detections: 0, flagLabel: null,
    initials: 'BD', avatarColor: '#bc8cff',
  },
  {
    name: 'David Wu', handle: 'david', team: 'platform-team',
    bars: [16, 20, 18, 14, 22, 18, 16],
    repos: 9, prs: 38, detections: 0, flagLabel: null,
    initials: 'DW', avatarColor: '#1f6feb',
  },
];

export function DevActivityPage() {
  const [activeTeam, setActiveTeam] = useState('All teams');

  const filteredDevs = activeTeam === 'All teams'
    ? DEVS
    : DEVS.filter((d) => d.team === activeTeam);

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Developer Activity</div>
      <div className={styles.pageSub}>Per-developer contribution metrics and security posture</div>

      <div className={styles.teamFilters}>
        {TEAMS.map((t) => (
          <Button
            key={t}
            size="sm"
            style={activeTeam === t ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}
            onClick={() => setActiveTeam(t)}
          >
            {t}
          </Button>
        ))}
      </div>

      <div className={styles.sectionTitle} style={{ marginBottom: 4 }}>Work distribution — last 30 days</div>
      <div className={styles.workNote}>
        Uneven distribution can indicate bus factor risk, burnout, or knowledge silos. Use to start conversations, not assign blame.
      </div>

      <div className={styles.workGrid}>
        <Card>
          <CardHeader>PR authorship share</CardHeader>
          <div className={styles.barList}>
            {PR_AUTHORS.map((a) => (
              <div key={a.handle} className={styles.barRow}>
                <span className={[styles.barHandle, a.muted && styles.muted].filter(Boolean).join(' ')}>
                  {a.muted ? a.handle : `@${a.handle}`}
                </span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${a.pct}%`, height: '100%', background: a.color, borderRadius: 4 }} />
                </div>
                <span className={styles.barPct}>{a.pct}%</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader>Review concentration</CardHeader>
          <div className={styles.barList}>
            {REVIEWERS.map((r) => (
              <div key={r.handle} className={styles.barRow}>
                <span className={styles.barHandle} style={r.danger ? { color: 'var(--danger)' } : r.warn ? { color: 'var(--attention)' } : undefined}>
                  @{r.handle}
                </span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${r.pct}%`, height: '100%', background: r.color, borderRadius: 4 }} />
                </div>
                <span className={styles.barPct} style={r.danger ? { color: 'var(--danger)' } : r.warn ? { color: 'var(--attention)' } : undefined}>
                  {r.pct}%
                </span>
              </div>
            ))}
          </div>
          <div className={styles.busWarning}>
            ⚠ <strong>@alice</strong> performs 44% of all reviews — consider a review rotation to reduce bus factor risk
          </div>
        </Card>
      </div>

      <div className={styles.sectionTitle} style={{ marginBottom: 16 }}>Developer cards</div>
      <div className={styles.devGrid}>
        {filteredDevs.map((dev) => (
          <div
            key={dev.handle}
            className={[styles.devCard, dev.flagged && styles.flagged].filter(Boolean).join(' ')}
          >
            <div className={styles.devTop}>
              <Avatar username={dev.handle} size={36} />
              <div>
                <div className={styles.devName}>
                  {dev.name}
                  {dev.flagLabel && (
                    <Label variant={dev.flagged ? 'danger' : 'attention'} className={styles.flagLabel}>
                      {dev.flagLabel}
                    </Label>
                  )}
                </div>
                <div className={styles.devHandle}>
                  <span className={styles.mention}>@{dev.handle}</span> · {dev.team}
                </div>
              </div>
            </div>
            <MiniBarChart data={dev.bars} color={dev.barColor ?? 'var(--success)'} />
            <div className={styles.devStats}>
              <span><strong>{dev.repos}</strong> repos</span>
              <span><strong>{dev.prs}</strong> PRs</span>
              {dev.detections > 0 ? (
                <span style={{ color: dev.flagged ? 'var(--danger)' : 'var(--attention)' }}>
                  <strong>{dev.detections}</strong> {dev.flagLabel && dev.flagLabel !== 'flagged' ? dev.flagLabel : 'detections'}
                </span>
              ) : (
                <span><strong>0</strong> flags</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
