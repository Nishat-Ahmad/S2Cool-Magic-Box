// -------------------------------------------------------------------------
// ControlSidebar.jsx — "Magic Box" parameter panel.
//
// All sliders and inputs update App-level state immediately so the chart
// re-renders without a network round-trip (zero-latency feel).
// -------------------------------------------------------------------------

/** Small helper to clamp a value. */
const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

export default function ControlSidebar({
  targetCop,
  onTargetCopChange,
  coolingThreshold,
  onCoolingThresholdChange,
  panelCount,
  onPanelCountChange,
  panelWattage,
  onPanelWattageChange,
}) {
  return (
    <aside className="flex flex-col gap-5 w-full lg:w-[312px] lg:min-w-[292px] rounded-lg bg-s2-card border border-s2-border p-4">
      {/* ---- Section: Magic Parameters ---- */}
      <h3 className="text-xs uppercase tracking-widest text-s2-muted">
        Magic Parameters
      </h3>

      {/* Target COP slider (3.0 – 15.0) */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] uppercase tracking-wider text-s2-muted">
          Target COP (Ideal):{" "}
          <span className="font-mono text-s2-text">{targetCop.toFixed(1)}</span>
        </label>
        <input
          type="range"
          min="3"
          max="15"
          step="0.1"
          value={targetCop}
          onChange={(e) => onTargetCopChange(Number(e.target.value))}
          className="w-full"
        />
      </div>

      {/* Cooling threshold slider (15°C – 30°C) */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] uppercase tracking-wider text-s2-muted">
          Cooling Threshold:{" "}
          <span className="font-mono text-s2-text">
            {coolingThreshold.toFixed(1)}°C
          </span>
        </label>
        <input
          type="range"
          min="15"
          max="30"
          step="0.5"
          value={coolingThreshold}
          onChange={(e) => onCoolingThresholdChange(Number(e.target.value))}
          className="w-full"
        />
      </div>

      {/* ---- Section: PV Infrastructure Config ---- */}
      <h3 className="text-xs uppercase tracking-widest text-s2-muted mt-1">
        PV Infrastructure Config
      </h3>

      {/* Panel count */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] uppercase tracking-wider text-s2-muted">
          Panel Count
        </label>
        <input
          type="number"
          min="1"
          step="1"
          value={panelCount}
          onChange={(e) =>
            onPanelCountChange(clamp(Number(e.target.value) || 1, 1, 200))
          }
          className="h-[34px] w-full rounded-lg border border-s2-border bg-[#0f0f12] text-s2-text px-2.5 text-sm font-mono"
        />
      </div>

      {/* Panel wattage */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] uppercase tracking-wider text-s2-muted">
          Individual Panel Wattage (W)
        </label>
        <input
          type="number"
          min="100"
          step="10"
          value={panelWattage}
          onChange={(e) =>
            onPanelWattageChange(
              clamp(Number(e.target.value) || 100, 100, 2000)
            )
          }
          className="h-[34px] w-full rounded-lg border border-s2-border bg-[#0f0f12] text-s2-text px-2.5 text-sm font-mono"
        />
      </div>

      {/* ---- Computed readout ---- */}
      <div className="mt-auto pt-4 border-t border-s2-border">
        <p className="text-[11px] uppercase tracking-wider text-s2-muted mb-1">
          Installed DC Capacity
        </p>
        <p className="text-lg font-bold font-mono text-s2-text">
          {((panelCount * panelWattage) / 1000).toFixed(2)} kW
          <span className="text-xs font-normal text-s2-muted ml-2">DC</span>
        </p>
      </div>
    </aside>
  );
}
