// -------------------------------------------------------------------------
// Header.jsx — Global control bar.
//
// Contains city dropdown, date picker, source-mode label, and the
// system heartbeat status pill.
// -------------------------------------------------------------------------

const CITIES = ["Islamabad", "Lahore", "Karachi", "Peshawar"];

/**
 * Pill background color map.
 * blue  = STANDBY (no cooling needed)
 * green = SOLAR PRIORITY
 * red   = GRID ACTIVE
 */
const PILL_STYLES = {
  blue: "border-s2-blue text-s2-blue",
  green: "border-emerald-500 text-emerald-500",
  red: "border-s2-red text-s2-red",
};

export default function Header({
  city,
  onCityChange,
  date,
  onDateChange,
  heartbeat,
  sourceMode,
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-s2-card border border-s2-border px-4 py-3">
      {/* ---- Brand + mode ---- */}
      <div className="flex flex-col gap-0.5 min-w-[240px]">
        <h1 className="text-base font-bold tracking-wide text-s2-text">
          S2Cool Enterprise Dashboard
        </h1>
        <p className="text-xs text-s2-muted">
          {sourceMode === "PREDICTION"
            ? "Prediction Mode: AI Forecast Engine"
            : "Historical Mode: Stored Daily Profile"}
        </p>
      </div>

      {/* ---- Controls row ---- */}
      <div className="flex flex-wrap items-end gap-3">
        {/* City selector */}
        <div className="flex flex-col gap-1 min-w-[172px]">
          <label className="text-[11px] uppercase tracking-wider text-s2-muted">
            Site / City
          </label>
          <select
            value={city}
            onChange={(e) => onCityChange(e.target.value)}
            className="h-[34px] rounded-lg border border-s2-border bg-[#0f0f12] text-s2-text px-2.5 text-sm font-sans"
          >
            {CITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {/* Date picker */}
        <div className="flex flex-col gap-1 min-w-[172px]">
          <label className="text-[11px] uppercase tracking-wider text-s2-muted">
            Date
          </label>
          <input
            type="date"
            value={date}
            onChange={(e) => onDateChange(e.target.value)}
            className="h-[34px] rounded-lg border border-s2-border bg-[#0f0f12] text-s2-text px-2.5 text-sm font-sans"
          />
        </div>

        {/* System heartbeat pill */}
        <div
          className={`flex items-center justify-center h-[34px] min-w-[220px]
            rounded-lg border font-semibold text-xs tracking-wide font-mono
            ${PILL_STYLES[heartbeat.color] || PILL_STYLES.blue}`}
        >
          {heartbeat.label}
        </div>
      </div>
    </header>
  );
}
