// -------------------------------------------------------------------------
// HeroKPIs.jsx — Top row of metric cards.
//
// All values are derived from chartData (the 24-hour array) so they
// update instantly when the user drags a slider.
// -------------------------------------------------------------------------
import { useMemo } from "react";

/** Individual KPI card. */
function KpiCard({ label, value, unit }) {
  return (
    <div className="flex flex-col gap-1.5 flex-1 min-w-[180px] rounded-lg bg-[#101014] border border-s2-border p-3">
      <span className="text-[11px] uppercase tracking-wider text-s2-muted">
        {label}
      </span>
      <span className="text-xl font-bold font-mono text-s2-text">
        {value}
        {unit && (
          <span className="text-xs font-normal text-s2-muted ml-1.5">
            {unit}
          </span>
        )}
      </span>
    </div>
  );
}

export default function HeroKPIs({ chartData }) {
  const metrics = useMemo(() => {
    if (!chartData || chartData.length === 0) {
      return {
        operatingPct: "0.0",
        peakGhi: "0",
        psh: "0.00",
        totalDeficit: "0.00",
      };
    }

    // System Operating %: hours where solar generation > 2 kW / 24
    const solarActiveHours = chartData.filter((r) => r.solarKw > 2).length;
    const operatingPct = ((solarActiveHours / 24) * 100).toFixed(1);

    // Peak GHI: max predicted GHI over the day
    const peakGhi = Math.max(...chartData.map((r) => r.ghi)).toFixed(0);

    // Calculated PSH: area under GHI curve = sum(hourly GHI) / 1000
    const psh = (
      chartData.reduce((acc, r) => acc + r.ghi, 0) / 1000
    ).toFixed(2);

    // Total Energy Deficit: sum of grid draw required
    const totalDeficit = chartData
      .reduce((acc, r) => acc + r.gridDeficit, 0)
      .toFixed(2);

    return { operatingPct, peakGhi, psh, totalDeficit };
  }, [chartData]);

  return (
    <section className="flex flex-wrap gap-2.5 rounded-lg bg-s2-card border border-s2-border p-3">
      <KpiCard
        label="System Operating"
        value={`${metrics.operatingPct}%`}
      />
      <KpiCard label="Peak GHI (Predicted)" value={metrics.peakGhi} unit="W/m2" />
      <KpiCard label="Calculated PSH" value={metrics.psh} unit="h" />
      <KpiCard
        label="Total Energy Deficit"
        value={metrics.totalDeficit}
        unit="kWh"
      />
    </section>
  );
}
