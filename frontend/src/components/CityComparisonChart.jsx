// -------------------------------------------------------------------------
// CityComparisonChart.jsx — 4-city GHI overlay + Operating % bar chart.
//
// Fetches /v1/compare/cities on date change and renders:
// 1. A multi-line Recharts chart with 4 distinct city GHI curves
// 2. A bar chart of each city's Operating %
// -------------------------------------------------------------------------
import { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const CITY_COLORS = {
  Islamabad: "#3b82f6",
  Lahore: "#fbbf24",
  Karachi: "#22d3ee",
  Peshawar: "#a78bfa",
};

function LegendChip({ color, label }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-s2-muted">
      <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

export default function CityComparisonChart({ date }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch("/v1/compare/cities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date_utc: date }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [date]);

  if (loading || !data) {
    return (
      <div className="rounded-lg bg-s2-card border border-s2-border p-6 text-center text-s2-muted text-sm">
        {loading ? "Loading city comparison..." : "No data"}
      </div>
    );
  }

  // Build a merged 24-hour array: { hour, Islamabad, Lahore, Karachi, Peshawar }
  const merged = Array.from({ length: 24 }, (_, h) => {
    const row = { hour: h, hourLabel: `${String(h).padStart(2, "0")}:00` };
    data.cities.forEach((c) => {
      row[c.city] = c.hours[h]?.predicted_ghi_wm2 ?? 0;
    });
    return row;
  });

  // Operating % bar data
  const opData = data.cities.map((c) => ({
    city: c.city,
    pct: c.operating_pct,
    color: CITY_COLORS[c.city] || "#71717a",
  }));

  return (
    <div className="flex flex-col gap-3">
      {/* GHI overlay */}
      <section className="rounded-lg bg-s2-card border border-s2-border p-3">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
          <h3 className="text-xs uppercase tracking-widest text-s2-muted">
            4-City GHI Comparison — {date}
          </h3>
          <div className="flex flex-wrap gap-3">
            {Object.entries(CITY_COLORS).map(([city, color]) => (
              <LegendChip key={city} color={color} label={city} />
            ))}
          </div>
        </div>
        <div style={{ height: 340 }}>
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
              {Object.entries(CITY_COLORS).map(([city, color]) => (
                <Line
                  key={city}
                  type="monotone"
                  dataKey={city}
                  stroke={color}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Operating % bar chart */}
      <section className="rounded-lg bg-s2-card border border-s2-border p-3">
        <h3 className="text-xs uppercase tracking-widest text-s2-muted mb-2.5">
          System Operating % by City
        </h3>
        <div style={{ height: 200 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={opData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
              <XAxis
                dataKey="city"
                stroke="#a1a1aa"
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
              />
              <YAxis
                domain={[0, 100]}
                stroke="#a1a1aa"
                tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
                label={{ value: "%", angle: -90, position: "insideLeft", fill: "#a1a1aa", fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 }}
              />
              <Bar dataKey="pct" name="Operating %" barSize={48}>
                {opData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
