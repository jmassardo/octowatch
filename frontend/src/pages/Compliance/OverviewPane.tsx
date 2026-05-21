import { Button } from '../../components/primitives/Button';
import { Card } from '../../components/primitives/Card';
import type { FrameworkScore, ComplianceSummary } from '../../types/compliance';
import styles from './Compliance.module.css';

function scoreColorClass(score: number): string {
  if (score >= 75) return styles.scoreHigh;
  if (score >= 50) return styles.scoreMedium;
  return styles.scoreLow;
}

function scoreBarColor(score: number): string {
  if (score >= 75) return 'var(--success)';
  if (score >= 50) return 'var(--attention)';
  return 'var(--danger)';
}

interface OverviewPaneProps {
  summary: ComplianceSummary | undefined;
  onSelectFramework: (name: string) => void;
  onGenerateAll: () => void;
  isGenerating: boolean;
}

export function OverviewPane({
  summary,
  onSelectFramework,
  onGenerateAll,
  isGenerating,
}: OverviewPaneProps) {
  if (!summary) return null;

  const frameworks = summary.frameworks;

  return (
    <div>
      <div className={styles.actionsBar}>
        <Button variant="primary" onClick={onGenerateAll} disabled={isGenerating}>
          {isGenerating ? 'Generating…' : 'Generate All Reports'}
        </Button>
      </div>

      {/* Radar chart placeholder */}
      <div className={styles.radarPlaceholder} aria-label="Compliance radar chart">
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📊</div>
          <div>Compliance Score Distribution</div>
          <div style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>
            {frameworks.map((fw) => `${fw.display_name}: ${fw.score}%`).join(' · ')}
          </div>
        </div>
      </div>

      {/* Framework cards */}
      <div className={styles.frameworkGrid}>
        {frameworks.map((fw) => (
          <FrameworkCard key={fw.name} framework={fw} onClick={() => onSelectFramework(fw.name)} />
        ))}
      </div>
    </div>
  );
}

function FrameworkCard({ framework, onClick }: { framework: FrameworkScore; onClick: () => void }) {
  return (
    <Card className={styles.frameworkCard} onClick={onClick}>
      <div className={styles.frameworkCardHeader}>
        <span className={styles.frameworkName}>{framework.display_name}</span>
        <span className={`${styles.frameworkScore} ${scoreColorClass(framework.score)}`}>
          {framework.score}%
        </span>
      </div>
      <div className={styles.progressBar}>
        <div
          className={styles.progressFill}
          style={{
            width: `${framework.score}%`,
            backgroundColor: scoreBarColor(framework.score),
          }}
        />
      </div>
      <div className={styles.frameworkMeta}>
        <span>
          {framework.controls_passing} / {framework.controls_total} controls passing
        </span>
        {framework.last_generated && (
          <>
            <span> · </span>
            <span>Last: {new Date(framework.last_generated).toLocaleDateString()}</span>
          </>
        )}
      </div>
    </Card>
  );
}
