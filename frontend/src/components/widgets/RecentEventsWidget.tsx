import styles from '../widgets/Widgets.module.css';

/** Recent Events widget — latest audit event stream. */
export function RecentEventsWidget() {
  return (
    <div className={styles.list}>
      {[
        { action: 'repo.create', actor: 'octocat', time: '2 min ago' },
        { action: 'team.add_member', actor: 'mona', time: '5 min ago' },
        { action: 'org.update_member', actor: 'hubot', time: '12 min ago' },
        { action: 'protected_branch.update', actor: 'octocat', time: '18 min ago' },
        { action: 'repo.destroy', actor: 'admin-bot', time: '25 min ago' },
      ].map((evt) => (
        <div key={`${evt.action}-${evt.time}`} className={styles.listItem}>
          <span className={styles.listLabel}>
            <strong>{evt.action}</strong> by {evt.actor}
          </span>
          <span className={styles.listValue}>{evt.time}</span>
        </div>
      ))}
    </div>
  );
}
