// -------------------------------------------------------------------------
// MainChart.jsx — Primary 24-hour ComposedChart (Recharts).
//
// Left Y-axis  : Power in kW  (Solar area, Load dashed line, Grid bars)
// Right Y-axis : Temperature in °C  (Ambient temp solid line)
//
// The Electrical Load line drops to 0 for any hour where ambient temp
// is below the cooling threshold — this is already computed in App.jsx's
// deriveChartSeries().
// -------------------------------------------------------------------------
import {
  ComposedChart,
  Area,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

/** Custom tooltip styled to match the dark theme. */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="rounded-lg bg-s2-card border border-s2-border px-3 py-2 text-xs">
      <p className="font-mono text-s2-text mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }} className="font-mono">
          {entry.name}: {Number(entry.value).toFixed(2)}
        </p>
      ))}
    </div>
  );
}

/** Legend chip — a simple colored dot + label. */
function LegendChip({ color, label }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-s2-muted">
      <span
        className="inline-block w-2 h-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

export default function MainChart({ chartData }) {
  return (
    <section className="flex flex-col flex-1 min-h-[380px] rounded-lg bg-s2-card border border-s2-border p-3">
      {/* ---- Chart header + legend ---- */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
        <h3 className="text-xs uppercase tracking-widest text-s2-muted">
          Primary Visualization
        </h3>
        <div className="flex flex-wrap gap-3">
          <LegendChip color="#fbbf24" label="Solar Gen (kW)" />
          <LegendChip color="#ef4444" label="Electrical Load (kW)" />
          <LegendChip color="#71717a" label="Grid Deficit (kW)" />
          <LegendChip color="#22d3ee" label="Ambient Temp (°C)" />
        </div>
      </div>

      {/* ---- Recharts ComposedChart ---- */}
      <div className="flex-1" style={{ minHeight: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 8, right: 28, left: 0, bottom: 8 }}
          >
            <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />

            {/* X-axis: hour labels */}
            <XAxis
              dataKey="hourLabel"
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
            />

            {/* Left Y-axis: Power (kW) */}
            <YAxis
              yAxisId="power"
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
              label={{
                value: "kW",
                angle: -90,
                position: "insideLeft",
                fill: "#a1a1aa",
                fontSize: 11,
              }}
            />

            {/* Right Y-axis: Temperature (°C) */}
            <YAxis
              yAxisId="temp"
              orientation="right"
              stroke="#22d3ee"
              tick={{ fill: "#22d3ee", fontSize: 11, fontFamily: "monospace" }}
              label={{
                value: "°C",
                angle: 90,
                position: "insideRight",
                fill: "#22d3ee",
                fontSize: 11,
              }}
            />

            <Tooltip content={<ChartTooltip />} />

            {/* Solar generation — filled area (Gold) */}
            <Area
              yAxisId="power"
              type="monotone"
              dataKey="solarKw"
              stroke="#fbbf24"
              fill="#fbbf24"
              fillOpacity={0.18}
              name="Solar Gen (kW)"
            />

            {/* Electrical load — dashed line (Red) */}
            <Line
              yAxisId="power"
              type="monotone"
              dataKey="loadKw"
              stroke="#ef4444"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              name="Electrical Load (kW)"
            />

            {/* Grid deficit — bar chart (Grey) */}
            <Bar
              yAxisId="power"
              dataKey="gridDeficit"
              fill="#71717a"
              name="Grid Deficit (kW)"
              barSize={14}
            />

            {/* Ambient temperature — solid line (Cyan), right axis */}
            <Line
              yAxisId="temp"
              type="monotone"
              dataKey="ambientTemp"
              stroke="#22d3ee"
              strokeWidth={1.5}
              dot={false}
              name="Ambient Temp (°C)"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
