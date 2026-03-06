// -------------------------------------------------------------------------
// BacktestChart.jsx — Actual vs Predicted GHI backtest for the last 7 days.
//
// Fetches /v1/ml/backtest?city=X and renders a dual-line chart:
// solid line = "actual" (historical), dashed = predicted.
// -------------------------------------------------------------------------
import { useState, useEffect, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function LegendChip({ color, label, dashed }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-s2-muted">
      <span
        className="inline-block w-4 h-0.5"
        style={{
          backgroundColor: color,
          borderTop: dashed ? `2px dashed ${color}` : `2px solid ${color}`,
        }}
      />
      {label}
    </span>
  );
}

export default function BacktestChart({ city }) {
  const [raw, setRaw] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/v1/ml/backtest?city=${encodeURIComponent(city)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setRaw(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [city]);

  // Flatten into sequential x-axis points (day-hour combos)
  const chartData = useMemo(() => {
    if (!raw) return [];
    return raw.points.map((p, i) => ({
      idx: i,
      label: `${p.date_utc.slice(5)} ${String(p.hour).padStart(2, "0")}h`,
      actual: p.actual_ghi,
      predicted: p.predicted_ghi,
    }));
  }, [raw]);

  if (loading || !raw) {
    return (
      <div className="rounded-lg bg-s2-card border border-s2-border p-6 text-center text-s2-muted text-sm">
        {loading ? "Loading backtest..." : "No data"}
      </div>
    );
  }

  return (
    <section className="rounded-lg bg-s2-card border border-s2-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
        <h3 className="text-xs uppercase tracking-widest text-s2-muted">
          7-Day Backtest: Actual vs Predicted GHI — {city}
        </h3>
        <div className="flex flex-wrap gap-3">
          <LegendChip color="#22d3ee" label="Actual GHI" />
          <LegendChip color="#fbbf24" label="Predicted GHI" dashed />
        </div>
      </div>
      <div style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 9, fontFamily: "monospace" }}
              interval={23}
            />
            <YAxis
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
              label={{ value: "W/m²", angle: -90, position: "insideLeft", fill: "#a1a1aa", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#f4f4f5", fontFamily: "monospace" }}
            />
            <Line type="monotone" dataKey="actual" stroke="#22d3ee" strokeWidth={1.5} dot={false} name="Actual GHI" />
            <Line type="monotone" dataKey="predicted" stroke="#fbbf24" strokeWidth={1.5} strokeDasharray="6 3" dot={false} name="Predicted GHI" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
