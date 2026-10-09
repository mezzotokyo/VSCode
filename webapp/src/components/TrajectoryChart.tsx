import type { TrajectoryPoint } from '../types'

interface TrajectoryChartProps {
  trajectory: TrajectoryPoint[]
  idealRange: number
  groundRange: number
}

const WIDTH = 940
const HEIGHT = 460
const MARGIN = { top: 28, right: 28, bottom: 52, left: 68 }

function niceStep(range: number, count: number): number {
  if (range <= 0) {
    return 1
  }
  const raw = range / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const normalized = raw / magnitude
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return nice * magnitude
}

function ticks(max: number, count: number): number[] {
  const step = niceStep(max, count)
  const values: number[] = []
  for (let value = 0; value <= max + step / 2; value += step) {
    values.push(Number(value.toFixed(6)))
  }
  return values
}

export function TrajectoryChart({
  trajectory,
  idealRange,
  groundRange,
}: TrajectoryChartProps) {
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom

  const maxX = Math.max(idealRange, groundRange, ...trajectory.map((p) => p.x), 1)
  const maxY = Math.max(...trajectory.map((p) => p.y), 1)
  const xDomain = maxX * 1.05
  const yDomain = maxY * 1.15

  const sx = (x: number) => MARGIN.left + (x / xDomain) * plotWidth
  const sy = (y: number) => MARGIN.top + plotHeight - (y / yDomain) * plotHeight

  const path = trajectory
    .map((p, index) => `${index === 0 ? 'M' : 'L'} ${sx(p.x).toFixed(2)} ${sy(p.y).toFixed(2)}`)
    .join(' ')

  const xTicks = ticks(xDomain, 6)
  const yTicks = ticks(yDomain, 5)
  const launch = trajectory[0]
  const landing = trajectory[trajectory.length - 1]

  return (
    <svg
      className="chart"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label="flight trajectory"
    >
      {yTicks.map((value) => (
        <g key={`y-${value}`}>
          <line
            x1={MARGIN.left}
            x2={MARGIN.left + plotWidth}
            y1={sy(value)}
            y2={sy(value)}
            className="grid"
          />
          <text x={MARGIN.left - 10} y={sy(value)} className="tick" textAnchor="end">
            {value.toFixed(0)}
          </text>
        </g>
      ))}

      {xTicks.map((value) => (
        <g key={`x-${value}`}>
          <line
            x1={sx(value)}
            x2={sx(value)}
            y1={MARGIN.top}
            y2={MARGIN.top + plotHeight}
            className="grid"
          />
          <text x={sx(value)} y={MARGIN.top + plotHeight + 20} className="tick" textAnchor="middle">
            {value.toFixed(0)}
          </text>
        </g>
      ))}

      <line
        x1={MARGIN.left}
        x2={MARGIN.left}
        y1={MARGIN.top}
        y2={MARGIN.top + plotHeight}
        className="axis"
      />
      <line
        x1={MARGIN.left}
        x2={MARGIN.left + plotWidth}
        y1={MARGIN.top + plotHeight}
        y2={MARGIN.top + plotHeight}
        className="axis"
      />

      {idealRange > 0 && (
        <g>
          <line
            x1={sx(idealRange)}
            x2={sx(idealRange)}
            y1={MARGIN.top}
            y2={MARGIN.top + plotHeight}
            className="ideal-line"
          />
          <text x={sx(idealRange) - 6} y={MARGIN.top + 14} className="ideal-label" textAnchor="end">
            ideal {idealRange.toFixed(1)} m
          </text>
        </g>
      )}

      {path && <path d={path} className="trajectory" />}

      {landing && (
        <circle cx={sx(landing.x)} cy={sy(landing.y)} r={5} className="landing-point" />
      )}
      {launch && <circle cx={sx(launch.x)} cy={sy(launch.y)} r={5} className="launch-point" />}

      <text
        x={MARGIN.left + plotWidth / 2}
        y={HEIGHT - 10}
        className="axis-label"
        textAnchor="middle"
      >
        horizontal distance x (m)
      </text>
      <text
        x={-(MARGIN.top + plotHeight / 2)}
        y={16}
        className="axis-label"
        textAnchor="middle"
        transform="rotate(-90)"
      >
        height y (m)
      </text>
    </svg>
  )
}
