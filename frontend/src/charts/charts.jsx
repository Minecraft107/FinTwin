// Charts follow the data-viz spec: categorical colours in fixed order (blue, orange, aqua),
// 2px lines, ~10% area washes, <=24px bars with 4px rounded data-ends, hairline solid
// horizontal grid, muted axes, a legend for >=2 series, and a hover tooltip on every chart.
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { inr, inrCompact, monthLabel } from '../utils/format'

const SERIES = ['#2a78d6', '#eb6834', '#1baf7a']
const MUTED = '#a8a39c'
const GRID = '#eae8e4'
const TICK = { fill: '#787774', fontSize: 12 }
const ACTIVE_DOT = { r: 4, stroke: '#ffffff', strokeWidth: 2 }

function ChartTooltip({ active, payload, label, labelFormatter = monthLabel, valueFormatter = inr }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-xs shadow-[0_8px_24px_-8px_rgba(31,30,28,0.16)]">
      <div className="mb-1 font-medium text-ink">{labelFormatter(label)}</div>
      {payload
        .filter((p) => p.value != null)
        .map((p) => (
          <div key={p.dataKey} className="flex items-center gap-2 text-ink-2">
            <span className="inline-block size-2 rounded-full" style={{ background: p.color ?? p.stroke }} />
            <span>{p.name}</span>
            <span className="tabular ml-auto pl-3 font-medium text-ink">
              {Array.isArray(p.value) ? `${valueFormatter(p.value[0])} – ${valueFormatter(p.value[1])}` : valueFormatter(p.value)}
            </span>
          </div>
        ))}
    </div>
  )
}

const legendProps = { iconType: 'plainline', iconSize: 14, wrapperStyle: { fontSize: 12, color: '#57534e' } }

function Axes({ xKey = 'period', xFormatter = monthLabel }) {
  return [
    <CartesianGrid key="grid" vertical={false} stroke={GRID} />,
    <XAxis key="x" dataKey={xKey} tickFormatter={xFormatter} tick={TICK} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={16} />,
    <YAxis key="y" tickFormatter={inrCompact} tick={TICK} tickLine={false} axisLine={false} width={56} />,
  ]
}

// Income vs spending per month (two series -> legend).
export function FlowChart({ data, height = 260, xFormatter = monthLabel }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        {Axes({ xFormatter })}
        <Tooltip content={<ChartTooltip labelFormatter={xFormatter} />} />
        <Legend {...legendProps} />
        <Line type="monotone" dataKey="income" name="Income" stroke={SERIES[0]} strokeWidth={2} dot={false} activeDot={ACTIVE_DOT} />
        <Line type="monotone" dataKey="expenses" name="Spending" stroke={SERIES[1]} strokeWidth={2} dot={false} activeDot={ACTIVE_DOT} />
      </LineChart>
    </ResponsiveContainer>
  )
}

// One series over time (cash balance, net worth...): the title names it, so no legend.
export function TrendChart({ data, dataKey, name, height = 220, xKey = 'period', xFormatter = monthLabel, valueFormatter = inr, yFormatter = inrCompact, domain }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey={xKey} tickFormatter={xFormatter} tick={TICK} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={16} />
        <YAxis tickFormatter={yFormatter} tick={TICK} tickLine={false} axisLine={false} width={56} domain={domain} />
        <Tooltip content={<ChartTooltip labelFormatter={xFormatter} valueFormatter={valueFormatter} />} />
        <Area type="monotone" dataKey={dataKey} name={name} stroke={SERIES[0]} strokeWidth={2} fill={SERIES[0]} fillOpacity={0.1} activeDot={ACTIVE_DOT} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// Single-series horizontal bars (categories have no order -> one colour, value at the tip).
export function CategoryBars({ data, nameKey = 'category', valueKey = 'total' }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 64, left: 8, bottom: 0 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey={nameKey} tick={TICK} tickLine={false} axisLine={false} width={120} />
        <Tooltip cursor={{ fill: '#f1efeb' }} content={<ChartTooltip labelFormatter={(l) => l} />} />
        <Bar dataKey={valueKey} name="Spent" fill={SERIES[0]} barSize={16} radius={[0, 4, 4, 0]}>
          <LabelList dataKey={valueKey} position="right" formatter={inrCompact} style={{ fill: '#57534e', fontSize: 12 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// History + forecast with its likely range. Forecast is the same quantity, so the same hue;
// it is dashed and carries a 10% wash for the range. Legend names all three marks.
export function ForecastChart({ history, forecast, valueKey = 'value', height = 280 }) {
  const rows = history.map((h) => ({ month: h.month, actual: h[valueKey] }))
  if (rows.length && forecast.length) rows[rows.length - 1].forecast = rows[rows.length - 1].actual
  forecast.forEach((f) => rows.push({ month: f.month, forecast: f[valueKey], range: [f.lower, f.upper] }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        {Axes({ xKey: 'month' })}
        <Tooltip content={<ChartTooltip />} />
        <Legend {...legendProps} />
        <Area type="monotone" dataKey="range" name="Likely range (80%)" stroke="none" fill={SERIES[0]} fillOpacity={0.1} />
        <Line type="monotone" dataKey="actual" name="Actual" stroke={SERIES[0]} strokeWidth={2} dot={false} activeDot={ACTIVE_DOT} />
        <Line type="monotone" dataKey="forecast" name="Forecast" stroke={SERIES[0]} strokeWidth={2} strokeDasharray="5 4" dot={false} activeDot={ACTIVE_DOT} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// Projected cash balance with its likely range (single quantity).
export function ProjectionChart({ points, height = 260 }) {
  const rows = points.map((p) => ({ month: p.month, balance: p.cash_balance, range: [p.cash_lower, p.cash_upper] }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        {Axes({ xKey: 'month' })}
        <Tooltip content={<ChartTooltip />} />
        <Legend {...legendProps} />
        <ReferenceLine y={0} stroke="#d6d3ce" />
        <Area type="monotone" dataKey="range" name="Likely range (80%)" stroke="none" fill={SERIES[0]} fillOpacity={0.1} />
        <Line type="monotone" dataKey="balance" name="Projected cash balance" stroke={SERIES[0]} strokeWidth={2} dot={false} activeDot={ACTIVE_DOT} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// What-if: the baseline is recessive grey, the scenario is the accent.
export function ScenarioChart({ timeline, metric, height = 300 }) {
  const rows = timeline.map((t) => ({ month: t.month, baseline: t.baseline[metric], scenario: t.scenario[metric] }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        {Axes({ xKey: 'month' })}
        <Tooltip content={<ChartTooltip />} />
        <Legend {...legendProps} />
        <ReferenceLine y={0} stroke="#d6d3ce" />
        <Line type="monotone" dataKey="baseline" name="Without the change" stroke={MUTED} strokeWidth={2} dot={false} activeDot={ACTIVE_DOT} />
        <Line type="monotone" dataKey="scenario" name="With the change" stroke={SERIES[0]} strokeWidth={2} dot={false} activeDot={ACTIVE_DOT} />
      </LineChart>
    </ResponsiveContainer>
  )
}
