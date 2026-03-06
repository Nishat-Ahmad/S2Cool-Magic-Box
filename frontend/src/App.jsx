// -------------------------------------------------------------------------
// App.jsx — Single source of truth for all dashboard state.
//
// Three tabs:
//   1. Live Controller   — interactive simulator (existing)
//   2. Comparative Analytics — 4-city + seasonal comparisons
//   3. ML Diagnostics    — backtest, model comparison, feature importance
//
// State lives here and is passed down as props.
// -------------------------------------------------------------------------
import { useState, useEffect, useMemo, useCallback } from "react";
import Header from "./components/Header";
import TabNav from "./components/TabNav";
import ControlSidebar from "./components/ControlSidebar";
import HeroKPIs from "./components/HeroKPIs";
import MainChart from "./components/MainChart";
import CoolingBanner from "./components/CoolingBanner";
import DiagnosticFooter from "./components/DiagnosticFooter";
import CityComparisonChart from "./components/CityComparisonChart";
import SeasonalChart from "./components/SeasonalChart";
import BacktestChart from "./components/BacktestChart";
import ModelComparisonChart from "./components/ModelComparisonChart";
import FeatureImportanceChart from "./components/FeatureImportanceChart";
import PipelineDetails from "./components/PipelineDetails";

// --------------- helpers ---------------

/** Return today as YYYY-MM-DD string. */
function todayISO() {
  const d = new Date();
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
}

/**
 * Derive a full 24-hour chart-ready series from the raw backend profile
 * combined with the current control-sidebar parameters.
 *
 * This runs on EVERY slider/input change so the chart updates instantly
 * without a network round-trip (local re-computation).
 */
function deriveChartSeries(
  rawHours,
  { panelCount, panelWattage, targetCop, coolingThreshold }
) {
  if (!rawHours || rawHours.length === 0) return [];

  const COOLING_CAPACITY_KW_THERMAL = 20; // project constant
  const dcKw = (panelCount * panelWattage) / 1000;
  const loadKwBase = COOLING_CAPACITY_KW_THERMAL / targetCop;
  const SYSTEM_EFFICIENCY = 0.85;

  return rawHours.map((pt) => {
    const hour = new Date(pt.timestamp_utc).getUTCHours();
    const ghi = pt.predicted_ghi_wm2;
    const temp = pt.predicted_ambient_temp_c;

    const solarKw = +(dcKw * (ghi / 1000) * SYSTEM_EFFICIENCY).toFixed(3);

    // Load drops to ZERO when ambient temp is below the cooling threshold
    const coolingNeeded = temp >= coolingThreshold;
    const loadKw = coolingNeeded ? +loadKwBase.toFixed(3) : 0;

    const gridDeficit = +Math.max(0, loadKw - solarKw).toFixed(3);

    return {
      hour,
      hourLabel: `${String(hour).padStart(2, "0")}:00`,
      ghi: +ghi.toFixed(2),
      ambientTemp: +temp.toFixed(2),
      solarKw,
      loadKw,
      gridDeficit,
    };
  });
}

// -------------------------------------------------------------------------
// Main App component
// -------------------------------------------------------------------------
export default function App() {
  // ---- Tab navigation ----
  const [activeTab, setActiveTab] = useState("controller");

  // ---- Global controls ----
  const [city, setCity] = useState("Lahore");
  const [date, setDate] = useState(todayISO());

  // ---- Sidebar parameters ----
  const [targetCop, setTargetCop] = useState(10.0);
  const [coolingThreshold, setCoolingThreshold] = useState(22.0);
  const [panelCount, setPanelCount] = useState(10);
  const [panelWattage, setPanelWattage] = useState(640);

  // ---- API state ----
  const [rawHours, setRawHours] = useState([]); // backend profile
  const [apiSummary, setApiSummary] = useState(null); // summary stats
  const [sourceMode, setSourceMode] = useState("HISTORICAL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ---- Production metrics (for footer) ----
  const [prodMetrics, setProdMetrics] = useState(null);

  // ------------------------------------------------------------------
  // Fetch production_metrics.json once on mount
  // ------------------------------------------------------------------
  useEffect(() => {
    fetch("/production_metrics.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setProdMetrics(data))
      .catch(() => {});
  }, []);

  // ------------------------------------------------------------------
  // Call /v1/simulate/day/auto when city, date, panelCount, or
  // panelWattage change (these are backend-dependent parameters).
  // ------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    fetch("/v1/simulate/day/auto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        city,
        date_utc: date,
        panel_count: panelCount,
        panel_watt_rating: panelWattage,
      }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`API ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setRawHours(data.hours || []);
        setApiSummary(data);
        setSourceMode(data.source_mode || "HISTORICAL");
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [city, date, panelCount, panelWattage]);

  // ------------------------------------------------------------------
  // Locally derive chart data on every parameter change (instant)
  // ------------------------------------------------------------------
  const chartData = useMemo(
    () =>
      deriveChartSeries(rawHours, {
        panelCount,
        panelWattage,
        targetCop,
        coolingThreshold,
      }),
    [rawHours, panelCount, panelWattage, targetCop, coolingThreshold]
  );

  // ------------------------------------------------------------------
  // Heartbeat status pill — computed from current hour's data
  // ------------------------------------------------------------------
  const heartbeat = useMemo(() => {
    const nowHour = new Date().getHours();
    const row = chartData.find((r) => r.hour === nowHour) || chartData[0];
    if (!row || row.loadKw <= 0) {
      return { label: "[ STANDBY: NO COOLING NEEDED ]", color: "blue" };
    }
    if (row.solarKw >= row.loadKw) {
      return { label: "[ SOLAR PRIORITY ]", color: "green" };
    }
    return { label: "[ GRID ACTIVE ]", color: "red" };
  }, [chartData]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="flex flex-col min-h-screen p-4 gap-3 max-w-[1600px] mx-auto">
      {/* ---- Top header bar ---- */}
      <Header
        city={city}
        onCityChange={setCity}
        date={date}
        onDateChange={setDate}
        heartbeat={heartbeat}
        sourceMode={sourceMode}
      />

      {/* ---- Tab navigation ---- */}
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />

      {/* ============================================================
          TAB 1: Live Controller
          ============================================================ */}
      {activeTab === "controller" && (
        <div className="flex flex-col lg:flex-row gap-3 flex-1 min-h-0">
          {/* Left sidebar — control parameters */}
          <ControlSidebar
            targetCop={targetCop}
            onTargetCopChange={setTargetCop}
            coolingThreshold={coolingThreshold}
            onCoolingThresholdChange={setCoolingThreshold}
            panelCount={panelCount}
            onPanelCountChange={setPanelCount}
            panelWattage={panelWattage}
            onPanelWattageChange={setPanelWattage}
          />

          {/* Right main area — KPIs, banner, chart, footer */}
          <main className="flex flex-col gap-3 flex-1 min-w-0">
            <HeroKPIs chartData={chartData} />
            <CoolingBanner chartData={chartData} coolingThreshold={coolingThreshold} />
            <MainChart chartData={chartData} coolingThreshold={coolingThreshold} />
            <DiagnosticFooter
              loading={loading}
              error={error}
              sourceMode={sourceMode}
              prodMetrics={prodMetrics}
            />
          </main>
        </div>
      )}

      {/* ============================================================
          TAB 2: Comparative Analytics
          ============================================================ */}
      {activeTab === "analytics" && (
        <div className="flex flex-col gap-3 flex-1">
          <CityComparisonChart date={date} />
          <SeasonalChart city={city} />
        </div>
      )}

      {/* ============================================================
          TAB 3: ML Diagnostics & Transparency
          ============================================================ */}
      {activeTab === "diagnostics" && (
        <div className="flex flex-col gap-3 flex-1">
          <BacktestChart city={city} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <ModelComparisonChart />
            <FeatureImportanceChart />
          </div>
          <PipelineDetails />
        </div>
      )}
    </div>
  );
}
