// -------------------------------------------------------------------------
// ModelComparisonChart.jsx — Bar chart comparing MAE/RMSE across models.
//
// Fetches /v1/ml/models and renders grouped bars: XGBoost vs LSTM.
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
  Legend,
} from "recharts";

export default function ModelComparisonChart() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch("/v1/ml/models")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return (
      <div className="rounded-lg bg-s2-card border border-s2-border p-6 text-center text-s2-muted text-sm">
        {loading ? "Loading model metrics..." : "No data"}
      </div>
    );
  }

  // Reshape: each model is a row with {model_name, MAE, RMSE, R²}
  const chartData = data.models.map((m) => ({
    model: m.model_name,
    MAE: m.mae,
    RMSE: m.rmse,
    "R²": m.r2,
  }));

  return (
    <section className="rounded-lg bg-s2-card border border-s2-border p-3">
      <h3 className="text-xs uppercase tracking-widest text-s2-muted mb-2.5">
        Model Performance Comparison
      </h3>
      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
            <XAxis
              dataKey="model"
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 10 }}
            />
            <YAxis
              stroke="#a1a1aa"
              tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "monospace" }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 }}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }}
            />
            <Bar dataKey="MAE" fill="#fbbf24" barSize={20} />
            <Bar dataKey="RMSE" fill="#ef4444" barSize={20} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
