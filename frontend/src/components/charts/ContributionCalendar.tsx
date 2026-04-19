import styles from './ContributionCalendar.module.css';

interface CalendarDay {
  date: string;
  level: 0 | 1 | 2 | 3 | 4;
  alert?: boolean;
}

interface ContributionCalendarProps {
  data?: CalendarDay[];
}

/** Generate an empty 90-day calendar (all level 0) when no real data is available. */
function generateEmptyData(): CalendarDay[] {
  const days: CalendarDay[] = [];
  const now = new Date();
  for (let i = 90; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    days.push({ date: d.toISOString().slice(0, 10), level: 0 });
  }
  return days;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['', 'Mon', '', 'Wed', '', 'Fri', ''];

export function ContributionCalendar({ data }: ContributionCalendarProps) {
  const days = data ?? generateEmptyData();

  // Group into weeks (columns)
  const weeks: CalendarDay[][] = [];
  let week: CalendarDay[] = [];
  for (const day of days) {
    const dow = new Date(day.date).getDay(); // 0=Sun
    if (week.length === 0 && dow !== 0) {
      for (let i = 0; i < dow; i++) week.push({ date: '', level: 0 });
    }
    week.push(day);
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  }
  if (week.length > 0) weeks.push(week);

  // Month labels
  const monthLabels: { label: string; col: number }[] = [];
  weeks.forEach((w, i) => {
    const d = w.find((x) => x.date)?.date;
    if (d) {
      const month = new Date(d).getMonth();
      if (i === 0 || new Date(weeks[i - 1]!.find((x) => x.date)?.date ?? '').getMonth() !== month) {
        monthLabels.push({ label: MONTHS[month] ?? '', col: i });
      }
    }
  });

  return (
    <div className={styles.wrap}>
      <div className={styles.months}>
        {monthLabels.map(({ label, col }) => (
          <span key={col} className={styles.monthLabel} style={{ gridColumnStart: col + 1 }}>
            {label}
          </span>
        ))}
      </div>
      <div className={styles.body}>
        <div className={styles.dayLabels}>
          {DAYS.map((d, i) => (
            <span key={i} className={styles.dayLabel}>
              {d}
            </span>
          ))}
        </div>
        <div className={styles.cols}>
          {weeks.map((w, wi) => (
            <div key={wi} className={styles.col}>
              {w.map((day, di) => (
                <div
                  key={di}
                  className={styles.cell}
                  data-level={day.alert ? undefined : day.level}
                  data-alert={day.alert ? '1' : undefined}
                  title={day.date}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
