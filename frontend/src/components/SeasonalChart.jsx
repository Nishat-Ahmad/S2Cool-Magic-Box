// -------------------------------------------------------------------------
// SeasonalChart.jsx — 4 seasonal average GHI curves for a given city.
//
// Fetches /v1/compare/seasonal?city=X and draws Summer / Spring /
// Winter / Autumn as four distinct lines.
// -------------------------------------------------------------------------
import { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const SEASON_COLORS = {
  Summer: "#fbbf24",
  Autumn: "#f97316",
  Winter: "#3b82f6",
  Spring: "#22c55e",
};

function LegendChip({ color, label }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-s2-muted">
      <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

export default function SeasonalChart({ city }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/v1/compare/seasonal?city=${encodeURIComponent(city)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [city]);

  if (loading || !data) {
    return (
      <div className="rounded-lg bg-s2-card border border-s2-border p-6 text-center text-s2-muted text-sm">
        {loading ? "Loading seasonal data..." : "No data"}
      </div>
    );
  }

  // Merge into a single row per hour: { hour, Summer, Autumn, Winter, Spring }
  const merged = Array.from({ length: 24 }, (_, h) => {
    const row = { hour: h, hourLabel: `${String(h).padStart(2, "0")}:00` };
    data.curves.forEach((curve) => {
      const pt = curve.hours.find((p) => p.hour === h);
      row[curve.season] = pt ? pt.avg_ghi_wm2 : 0;
    });
    return row;
  });

  return (
    <section className="rounded-lg bg-s2-card border border-s2-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
        <h3 className="text-xs uppercase tracking-widest text-s2-muted">
          Seasonal GHI Variation — {city}
        </h3>
        <div className="flex flex-wrap gap-3">
          {Object.entries(SEASON_COLORS).map(([s, color]) => (
            <LegendChip key={s} color={color} label={s} />
          ))}
        </div>
      </div>
      <div style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={merged} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
            <XAxis
              dataKey="hourLabel"
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
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
            {Object.entries(SEASON_COLORS).map(([season, color]) => (
              <Line
                key={season}
                type="monotone"
                dataKey={season}
                stroke={color}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
