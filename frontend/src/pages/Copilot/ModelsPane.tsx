import { Card, CardHeader } from '../../components/primitives/Card';
import { MODEL_USAGE, FEATURE_USAGE, EDITORS } from './copilotData';
import styles from './Copilot.module.css';

export function ModelsPane() {
  const maxFeatureCount = Math.max(...FEATURE_USAGE.map((f) => f.count));

  return (
    <>
      <div className={styles.grid2}>
        {/* Model usage spread */}
        <Card>
          <CardHeader>Model usage spread</CardHeader>
          <div className={styles.langBars}>
            {MODEL_USAGE.map((m) => (
              <div key={m.model} className={styles.langRow}>
                <span className={styles.langName} style={{ width: 100 }}>
                  {m.model}
                </span>
                <div className={styles.langTrack}>
                  <div
                    style={{
                      width: `${m.pct}%`,
                      height: '100%',
                      background: m.color,
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span className={styles.langPct}>{m.pct}%</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Feature usage spread */}
        <Card>
          <CardHeader>Feature usage spread</CardHeader>
          <div className={styles.langBars}>
            {FEATURE_USAGE.map((f) => (
              <div key={f.feature} className={styles.langRow}>
                <span className={styles.langName} style={{ width: 120 }}>
                  {f.feature}
                </span>
                <div className={styles.langTrack}>
                  <div
                    style={{
                      width: `${(f.count / maxFeatureCount) * 100}%`,
                      height: '100%',
                      background: f.color,
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span className={styles.langPct}>{f.count}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Editor breakdown */}
      <div className={styles.sectionTitle}>Editor breakdown</div>
      <div className={styles.editorGrid}>
        {EDITORS.map((e) => (
          <Card key={e.name} className={styles.editorCard}>
            <div className={styles.editorCount}>{e.count}</div>
            <div className={styles.editorName}>{e.name}</div>
            <div className={styles.editorPct}>{e.pct}%</div>
          </Card>
        ))}
      </div>
    </>
  );
}
