// -------------------------------------------------------------------------
// FeatureImportanceChart.jsx — Horizontal bar chart of XGBoost features.
//
// Fetches /v1/ml/feature-importance and renders a horizontal Recharts
// BarChart sorted by importance descending.
// -------------------------------------------------------------------------
import { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function FeatureImportanceChart() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch("/v1/ml/feature-importance")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return (
      <div className="rounded-lg bg-s2-card border border-s2-border p-6 text-center text-s2-muted text-sm">
        {loading ? "Loading features..." : "No data"}
      </div>
    );
  }

  // Sort descending by importance
  const sorted = [...data.features].sort((a, b) => b.importance - a.importance);
  const chartData = sorted.map((f) => ({
    feature: f.feature,
    importance: +(f.importance * 100).toFixed(1),
  }));

  return (
    <section className="rounded-lg bg-s2-card border border-s2-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
        <h3 className="text-xs uppercase tracking-widest text-s2-muted">
          XGBoost Feature Importance — {data.model_name}
        </h3>
      </div>
      <div style={{ height: Math.max(260, chartData.length * 32) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 4, right: 24, left: 110, bottom: 4 }}
          >
            <CartesianGrid stroke="#27272a" strokeDasharray="3 3" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, "dataMax + 2"]}
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
              label={{ value: "Importance %", position: "insideBottom", fill: "#a1a1aa", fontSize: 11, offset: -2 }}
            />
            <YAxis
              type="category"
              dataKey="feature"
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
              width={100}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 }}
            />
            <Bar dataKey="importance" fill="#3b82f6" barSize={18} name="Importance %" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
