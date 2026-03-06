// -------------------------------------------------------------------------
// CoolingBanner.jsx — Dynamic "NO COOLING NEEDED" banner + temp curve.
//
// Scans chartData: if ALL hours have loadKw === 0 (temp never exceeds
// the cooling threshold), show a prominent green banner. Otherwise show
// a compact summary of hours that DO need cooling.
// -------------------------------------------------------------------------
import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

export default function CoolingBanner({ chartData, coolingThreshold }) {
  const stats = useMemo(() => {
    if (!chartData || chartData.length === 0)
      return { allBelow: false, coolingHours: 0, peakTemp: 0 };
    const coolingHours = chartData.filter((r) => r.loadKw > 0).length;
    const peakTemp = Math.max(...chartData.map((r) => r.ambientTemp));
    return { allBelow: coolingHours === 0, coolingHours, peakTemp };
  }, [chartData]);

  return (
    <section className="rounded-lg bg-s2-card border border-s2-border p-3">
      {/* Banner text */}
      {stats.allBelow ? (
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span className="text-sm font-bold tracking-wide text-emerald-400">
            NO COOLING NEEDED — All hours below {coolingThreshold}°C threshold
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-s2-red" />
          <span className="text-sm font-bold tracking-wide text-s2-red">
            {stats.coolingHours}h cooling required — Peak {stats.peakTemp.toFixed(1)}°C
          </span>
        </div>
      )}

      {/* Mini temperature curve with threshold reference line */}
      <div style={{ height: 100 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="tempGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="hourLabel"
              tick={{ fill: "#a1a1aa", fontSize: 9, fontFamily: "monospace" }}
              interval={5}
              stroke="#27272a"
            />
            <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
            <ReferenceLine
              y={coolingThreshold}
              stroke="#ef4444"
              strokeDasharray="4 4"
              label={{ value: `${coolingThreshold}°C`, fill: "#ef4444", fontSize: 10, position: "right" }}
            />
            <Area
              type="monotone"
              dataKey="ambientTemp"
              stroke="#22d3ee"
              fill="url(#tempGrad)"
              strokeWidth={1.5}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
