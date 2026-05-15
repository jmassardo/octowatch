import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useChartColors } from '../../hooks/useChartColors';
import { describeGeoMap } from '../../utils/chartA11y';

interface GeoPoint {
  lat: number;
  lng: number;
  city: string;
  country: string;
}

interface GeoMapProps {
  locations: readonly GeoPoint[];
  height?: number;
}

/**
 * Simple geo scatter visualization using ECharts.
 *
 * Renders location points on a plain coordinate scatter plot
 * (longitude on X, latitude on Y) with connecting lines between
 * consecutive points. No external map tiles required.
 */
export function GeoMap({ locations, height = 300 }: GeoMapProps) {
  const colors = useChartColors();

  if (locations.length === 0) return null;

  // Build scatter data
  const scatterData = locations.map((loc) => ({
    value: [loc.lng, loc.lat],
    name: `${loc.city}${loc.city && loc.country ? ', ' : ''}${loc.country}`,
  }));

  // Build lines between consecutive locations
  const lineData: { coords: [number, number][] }[] = [];
  for (let i = 0; i < locations.length - 1; i++) {
    lineData.push({
      coords: [
        [locations[i].lng, locations[i].lat],
        [locations[i + 1].lng, locations[i + 1].lat],
      ],
    });
  }

  // Calculate distance between first and last point
  let distanceKm = 0;
  if (locations.length >= 2) {
    const first = locations[0];
    const last = locations[locations.length - 1];
    distanceKm = haversineDistance(first.lat, first.lng, last.lat, last.lng);
  }

  const option: EChartsOption = {
    backgroundColor: colors.chartBg,
    tooltip: {
      trigger: 'item',
    },
    xAxis: {
      type: 'value',
      min: -180,
      max: 180,
      show: false,
    },
    yAxis: {
      type: 'value',
      min: -90,
      max: 90,
      show: false,
    },
    grid: {
      left: 0,
      right: 0,
      top: 0,
      bottom: distanceKm > 0 ? 30 : 0,
    },
    graphic:
      distanceKm > 0
        ? [
            {
              type: 'text',
              left: 'center',
              bottom: 8,
              style: {
                text: `Distance: ${Math.round(distanceKm).toLocaleString()} km`,
                fill: colors.chartText,
                fontSize: 12,
              },
            },
          ]
        : [],
    series: [
      {
        type: 'scatter',
        coordinateSystem: 'cartesian2d',
        data: scatterData,
        symbolSize: 14,
        itemStyle: {
          color: colors.danger,
          borderColor: colors.canvas,
          borderWidth: 2,
        },
        label: {
          show: true,
          position: 'top',
          formatter: '{b}',
          color: colors.chartTooltipFg,
          fontSize: 11,
        },
      },
      {
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        data: lineData,
        lineStyle: {
          color: colors.danger,
          width: 2,
          type: 'dashed',
          curveness: 0.2,
        },
        effect: {
          show: true,
          period: 4,
          trailLength: 0.3,
          symbol: 'arrow',
          symbolSize: 6,
          color: colors.danger,
        },
      },
    ],
  };

  const ariaLabel = describeGeoMap(locations);

  return (
    <div role="figure" aria-label={ariaLabel}>
      <ReactECharts option={option} style={{ height }} />
      <table className="sr-only">
        <caption>Location data</caption>
        <thead>
          <tr>
            <th scope="col">City</th>
            <th scope="col">Country</th>
            <th scope="col">Latitude</th>
            <th scope="col">Longitude</th>
          </tr>
        </thead>
        <tbody>
          {locations.map((loc, i) => (
            <tr key={i}>
              <td>{loc.city}</td>
              <td>{loc.country}</td>
              <td>{loc.lat}</td>
              <td>{loc.lng}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Haversine distance between two lat/lng points in kilometers. */
function haversineDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371; // Earth radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) *
      Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}
