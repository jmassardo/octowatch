import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { LanguageBreakdownPane } from './LanguageBreakdownPane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockGetCopilotLanguageBreakdown = vi.fn();

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotLanguageBreakdown: (...args: unknown[]) => mockGetCopilotLanguageBreakdown(...args),
}));

describe('LanguageBreakdownPane', () => {
  beforeEach(() => {
    mockGetCopilotLanguageBreakdown.mockResolvedValue({
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      language_per_day: {
        TypeScript: [500, 520, 540],
        Python: [400, 410, 420],
      },
      language_distribution: [
        { name: 'TypeScript', value: 1560, color: '#3178c6' },
        { name: 'Python', value: 1230, color: '#3572a5' },
      ],
      model_per_language: {
        labels: ['TypeScript', 'Python'],
        series: [
          { name: 'gpt-4o', data: [500, 400] },
          { name: 'claude-3.5', data: [300, 350] },
        ],
      },
      acceptance_by_editor: [
        { editor: 'VS Code', rate: 38.5 },
        { editor: 'JetBrains', rate: 32.1 },
      ],
      top_by_generations: [
        { language: 'TypeScript', count: 12000 },
        { language: 'Python', count: 9500 },
      ],
      top_by_lines: [
        { language: 'TypeScript', lines: 45000 },
        { language: 'Python', lines: 32000 },
      ],
    });
  });

  it('renders language usage per day chart', async () => {
    renderWithProviders(<LanguageBreakdownPane />);
    expect(await screen.findByText('Language usage per day')).toBeInTheDocument();
  });

  it('renders language distribution donut', async () => {
    renderWithProviders(<LanguageBreakdownPane />);
    expect(await screen.findByText('Language distribution')).toBeInTheDocument();
  });

  it('renders model usage per language chart', async () => {
    renderWithProviders(<LanguageBreakdownPane />);
    expect(await screen.findByText('Model usage per language')).toBeInTheDocument();
  });

  it('renders acceptance rate by editor chart', async () => {
    renderWithProviders(<LanguageBreakdownPane />);
    expect(await screen.findByText('Acceptance rate by editor')).toBeInTheDocument();
  });

  it('renders top 5 by generations chart', async () => {
    renderWithProviders(<LanguageBreakdownPane />);
    expect(await screen.findByText('Top 5 languages by code generations')).toBeInTheDocument();
  });

  it('renders top 5 by lines chart', async () => {
    renderWithProviders(<LanguageBreakdownPane />);
    expect(await screen.findByText('Top 5 languages by lines added')).toBeInTheDocument();
  });
});
