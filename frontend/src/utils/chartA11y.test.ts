import { describe, it, expect } from 'vitest';
import {
  describeBarChart,
  describeLineAreaChart,
  describeGeoMap,
  chartToTableData,
} from './chartA11y';

describe('chartA11y', () => {
  describe('describeBarChart', () => {
    it('generates description with title', () => {
      const result = describeBarChart('Revenue', ['Q1', 'Q2', 'Q3'], [
        { name: 'Sales', data: [10, 20, 30] },
      ]);
      expect(result).toContain('Revenue');
      expect(result).toContain('Bar chart');
      expect(result).toContain('Sales: total 60');
      expect(result).toContain('3 categories');
    });

    it('generates description without title', () => {
      const result = describeBarChart(undefined, ['A', 'B'], [
        { name: 'Count', data: [5, 10] },
      ]);
      expect(result).not.toContain('undefined');
      expect(result).toContain('Bar chart');
      expect(result).toContain('Count: total 15');
    });

    it('handles multiple series', () => {
      const result = describeBarChart('Multi', ['X'], [
        { name: 'A', data: [10] },
        { name: 'B', data: [20] },
      ]);
      expect(result).toContain('A: total 10');
      expect(result).toContain('B: total 20');
    });
  });

  describe('describeLineAreaChart', () => {
    it('generates description with min/max values', () => {
      const result = describeLineAreaChart('Trend', ['Jan', 'Feb', 'Mar'], [
        { name: 'Users', data: [100, 200, 150] },
      ]);
      expect(result).toContain('Trend');
      expect(result).toContain('Line chart');
      expect(result).toContain('Users: values from 100 to 200');
      expect(result).toContain('3 points');
    });
  });

  describe('describeGeoMap', () => {
    it('describes locations', () => {
      const result = describeGeoMap([
        { city: 'New York', country: 'US' },
        { city: 'London', country: 'UK' },
      ]);
      expect(result).toContain('2 locations');
      expect(result).toContain('New York, US');
      expect(result).toContain('London, UK');
    });

    it('handles empty locations', () => {
      const result = describeGeoMap([]);
      expect(result).toContain('no locations');
    });

    it('handles single location', () => {
      const result = describeGeoMap([{ city: 'Tokyo', country: 'JP' }]);
      expect(result).toContain('1 location');
    });
  });

  describe('chartToTableData', () => {
    it('converts series to table rows and headers', () => {
      const result = chartToTableData('Month', ['Jan', 'Feb'], [
        { name: 'Sales', data: [10, 20] },
        { name: 'Returns', data: [1, 2] },
      ]);
      expect(result.headers).toEqual(['Month', 'Sales', 'Returns']);
      expect(result.rows).toEqual([
        ['Jan', 10, 1],
        ['Feb', 20, 2],
      ]);
    });

    it('handles missing data points', () => {
      const result = chartToTableData('X', ['A', 'B', 'C'], [
        { name: 'Y', data: [1] },
      ]);
      expect(result.rows).toEqual([
        ['A', 1],
        ['B', 0],
        ['C', 0],
      ]);
    });
  });
});
