import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import DataTable from "./DataTable";

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg bg-[#101014] border border-s2-border p-2 text-xs font-mono shadow-lg">
      {label != null && <p className="text-s2-muted mb-1">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || p.stroke || "#fbbf24" }}>
          {p.name}: {typeof p.value === "number" ? p.value.toFixed(2) : p.value}
        </p>
      ))}
    </div>
  );
}

function SectionCard({ title, sub, children }) {
  return (
    <section className="rounded-lg bg-s2-card border border-s2-border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h3 className="text-xs uppercase tracking-widest text-s2-muted">{title}</h3>
        {sub && <span className="text-[11px] text-s2-muted">{sub}</span>}
      </div>
      {children}
    </section>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="rounded-lg bg-[#101014] border border-s2-border p-3 text-center">
      <p className="text-[10px] uppercase tracking-widest text-s2-muted mb-1">{label}</p>
      <p className="text-xl font-bold text-s2-text font-mono">{value}</p>
      {sub && <p className="text-[10px] text-s2-muted mt-0.5">{sub}</p>}
    </div>
  );
}

export default function DriveDatasetInsights() {
  const [fileUrl, setFileUrl] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [folderUrl, setFolderUrl] = useState("");
  const [folderFiles, setFolderFiles] = useState([]);
  const [folderLoading, setFolderLoading] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(null);

  // Load info about how to use this feature on mount
  useEffect(() => {
    fetch("/v1/drive/info")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setInfo(d))
      .catch(() => {});
  }, []);

  // Fetch data when user submits URL
  const handleFetchFile = async (e) => {
    e?.preventDefault();
    if (!fileUrl.trim()) {
      setError("Please paste a file URL");
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");
    setData(null);

    try {
      const res = await fetch("/v1/drive/fetch-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_url: fileUrl.trim() }),
      });
      if (!res.ok) throw new Error(`API ${res.status}`);
      const d = await res.json();
      if (!cancelled) {
        setData(d);
        setLoading(false);
      }
    } catch (err) {
      if (!cancelled) {
        setError(err.message);
        setLoading(false);
      }
    }
  };

  const handleUploadFile = async (e) => {
    e?.preventDefault();
    if (!selectedFile) {
      setError("Please choose a CSV/XLSX file to upload");
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");
    setData(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const res = await fetch("/v1/drive/upload-file", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(`API ${res.status}`);
      const d = await res.json();
      if (!cancelled) {
        setData(d);
        setLoading(false);
      }
    } catch (err) {
      if (!cancelled) {
        setError(err.message);
        setLoading(false);
      }
    }
  };

  const handleListFolderFiles = async (e) => {
    e?.preventDefault();
    if (!folderUrl.trim()) {
      setError("Please paste a Google Drive folder URL");
      return;
    }

    setFolderLoading(true);
    setError("");
    setFolderFiles([]);

    try {
      const res = await fetch("/v1/drive/list-files", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_url: folderUrl.trim() }),
      });
      if (!res.ok) throw new Error(`API ${res.status}`);
      const d = await res.json();
      setFolderFiles(d.files || []);
      setFolderLoading(false);
    } catch (err) {
      setError(err.message);
      setFolderLoading(false);
    }
  };

  const handleSelectDriveFile = async (file) => {
    setLoading(true);
    setError("");
    setData(null);

    try {
      const res = await fetch(
        `/v1/drive/fetch-drive-file?file_id=${encodeURIComponent(file.id)}&file_name=${encodeURIComponent(file.name)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`API ${res.status}`);
      const d = await res.json();
      setData(d);
      setLoading(false);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  const freshnessLabel = useMemo(() => {
    if (!data?.fetch_timestamp_utc) return "Paste a public file URL to load data";
    const ts = new Date(data.fetch_timestamp_utc);
    const sourceFile = data.source_file_name || "uploaded file";
    return `Fetched: ${ts.toLocaleString()} | File: ${sourceFile}`;
  }, [data]);

  const allIngestedColumns = useMemo(() => {
    if (!data?.timeseries?.length) {
      return [
        { key: "timestamp_utc", label: "Timestamp" },
        { key: "city", label: "City" },
        { key: "ghi", label: "GHI (W/m2)", decimals: 2 },
        { key: "temp", label: "Temp (C)", decimals: 2 },
      ];
    }

    const preferredOrder = [
      "timestamp_utc",
      "city",
      "power_avg_w",
      "ghi_w_m2",
      "dni_w_m2",
      "dhi_w_m2",
      "ambient_temp_c",
      "relative_humidity_pct",
      "wind_speed_m_s",
    ];

    const labelByKey = {
      timestamp_utc: "Timestamp",
      city: "City",
      power_avg_w: "Power (W)",
      ghi_w_m2: "GHI (W/m2)",
      dni_w_m2: "DNI (W/m2)",
      dhi_w_m2: "DHI (W/m2)",
      ambient_temp_c: "Temp (C)",
      relative_humidity_pct: "Humidity (%)",
      wind_speed_m_s: "Wind (m/s)",
    };

    const hasDataForKey = (key) => data.timeseries.some((row) => row[key] != null);

    return preferredOrder
      .filter((key) => key === "timestamp_utc" || key === "city" || hasDataForKey(key))
      .map((key) => ({
        key,
        label: labelByKey[key] || key,
        ...(key !== "timestamp_utc" && key !== "city" ? { decimals: 2 } : {}),
      }));
  }, [data]);

  const allIngestedRows = useMemo(() => {
    if (data?.timeseries?.length) return data.timeseries.slice(0, 120);
    return data?.recent?.slice(-50) || [];
  }, [data]);

  return (
    <div className="flex flex-col gap-3 flex-1">
      {/* URL input section */}
      <SectionCard title="Public File URL" sub="No authentication required">
        <form onSubmit={handleFetchFile} className="flex flex-col gap-3">
          <div>
            <label className="block text-xs text-s2-muted mb-1 uppercase tracking-widest">
              Paste CSV or XLSX URL
            </label>
            <input
              type="text"
              placeholder="https://drive.google.com/uc?id=... or https://example.com/data.csv"
              value={fileUrl}
              onChange={(e) => setFileUrl(e.target.value)}
              disabled={loading}
              className="w-full px-3 py-2 bg-[#101014] border border-s2-border text-s2-text rounded text-sm focus:outline-none focus:ring-1 focus:ring-s2-accent font-mono text-xs"
            />
            <p className="text-xs text-s2-muted mt-1">
              ✓ Google Drive share links (paste as-is, app converts)
              <br />✓ Direct download URLs (CSV/XLSX)
              <br />✗ Private files (must be public or shared with link)
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleFetchFile}
              disabled={loading || !fileUrl.trim()}
              className="px-3 py-2 bg-white text-black rounded text-xs font-semibold hover:bg-neutral-200 disabled:opacity-50 transition w-fit"
            >
              {loading ? "Parsing..." : "Load & Visualize"}
            </button>
          </div>

          <div className="border-t border-s2-border pt-3">
            <label className="block text-xs text-s2-muted mb-1 uppercase tracking-widest">
              Or Upload Local File
            </label>
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              disabled={loading}
              className="w-full px-3 py-2 bg-[#101014] border border-s2-border text-s2-text rounded text-xs file:mr-3 file:px-2 file:py-1 file:border-0 file:rounded file:bg-white file:text-black file:text-xs"
            />
            <p className="text-xs text-s2-muted mt-1">
              Upload CSV/XLSX directly from your device.
              {selectedFile ? ` Selected: ${selectedFile.name}` : ""}
            </p>
            <button
              type="button"
              onClick={handleUploadFile}
              disabled={loading || !selectedFile}
              className="mt-2 px-3 py-2 bg-white text-black rounded text-xs font-semibold hover:bg-neutral-200 disabled:opacity-50 transition w-fit"
            >
              {loading ? "Uploading..." : "Upload & Visualize"}
            </button>
          </div>

          <div className="border-t border-s2-border pt-3">
            <label className="block text-xs text-s2-muted mb-1 uppercase tracking-widest">
              Or Browse Public Google Drive Folder
            </label>
            <input
              type="text"
              placeholder="https://drive.google.com/drive/folders/{FOLDER_ID}"
              value={folderUrl}
              onChange={(e) => setFolderUrl(e.target.value)}
              disabled={folderLoading || loading}
              className="w-full px-3 py-2 bg-[#101014] border border-s2-border text-s2-text rounded text-xs focus:outline-none focus:ring-1 focus:ring-s2-accent font-mono text-xs"
            />
            <p className="text-xs text-s2-muted mt-1">
              Public folder URL with CSV/XLSX files. Requires GOOGLE_DRIVE_API_KEY environment variable.
            </p>
            <button
              type="button"
              onClick={handleListFolderFiles}
              disabled={folderLoading || loading || !folderUrl.trim()}
              className="mt-2 px-3 py-2 bg-white text-black rounded text-xs font-semibold hover:bg-neutral-200 disabled:opacity-50 transition w-fit"
            >
              {folderLoading ? "Loading..." : "List Files"}
            </button>

            {folderFiles.length > 0 && (
              <div className="mt-3 bg-[#101014] border border-s2-border rounded p-3">
                <p className="text-xs text-s2-muted mb-2 uppercase tracking-widest">Available Files ({folderFiles.length})</p>
                <div className="space-y-1 max-h-[200px] overflow-y-auto">
                  {folderFiles.map((file) => (
                    <button
                      key={file.id}
                      onClick={() => handleSelectDriveFile(file)}
                      disabled={loading}
                      className="w-full text-left px-2 py-1.5 bg-[#0c0c0f] hover:bg-[#1a1a20] border border-s2-border rounded text-xs text-s2-text font-mono transition disabled:opacity-50"
                    >
                      <div className="flex items-center justify-between">
                        <span className="truncate">{file.name}</span>
                        <span className="text-s2-muted text-[10px] ml-2">
                          {file.size ? `${(file.size / 1024 / 1024).toFixed(1)}MB` : ""}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </form>

        {info && (
          <details className="mt-3 text-xs cursor-pointer">
            <summary className="text-s2-muted font-semibold">Show column format examples</summary>
            <div className="mt-2 p-2 rounded bg-[#101014] text-s2-muted font-mono text-[10px] whitespace-pre-wrap">
              {JSON.stringify(info.required_columns, null, 2)}
            </div>
          </details>
        )}
      </SectionCard>

      {error && (
        <div className="rounded-lg bg-[#3f1f1f] border border-[#7f1f1f] p-3 text-xs text-s2-red">
          Error: {error}
        </div>
      )}

      {data && !loading && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <StatCard label="Rows" value={data.total_points} sub="parsed points" />
            <StatCard
              label="Daily Avg GHI"
              value={
                data.daily.length > 0
                  ? `${(data.daily.reduce((acc, d) => acc + (d.avg_ghi || 0), 0) / data.daily.length).toFixed(1)} W/m²`
                  : "N/A"
              }
              sub="from available days"
            />
            <StatCard
              label="Daily Avg Temp"
              value={
                data.daily.length > 0
                  ? `${(data.daily.reduce((acc, d) => acc + (d.avg_temp || 0), 0) / data.daily.length).toFixed(1)} °C`
                  : "N/A"
              }
              sub="from available days"
            />
            <StatCard label="Cities" value={data.by_city.length} sub="distinct city profiles" />
          </div>

          <SectionCard title="Data Info" sub={freshnessLabel}>
            <p className="text-xs text-s2-muted">
              Data is parsed on-demand from a public URL. No database storage or authentication required.
            </p>
          </SectionCard>

          {data.daily.length > 0 && (
            <SectionCard title="Daily Trend" sub="Average GHI and ambient temperature by day">
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={data.daily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="date_utc" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <YAxis yAxisId="ghi" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <YAxis yAxisId="temp" orientation="right" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />
                  <Line yAxisId="ghi" type="monotone" dataKey="avg_ghi" stroke="#fbbf24" name="Avg GHI (W/m²)" dot={false} />
                  <Line yAxisId="temp" type="monotone" dataKey="avg_temp" stroke="#22d3ee" name="Avg Temp (°C)" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </SectionCard>
          )}

          {data.by_city.length > 0 && (
            <SectionCard title="City Comparison" sub="Average metrics by city">
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={data.by_city}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="city" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#71717a", fontSize: 10 }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />
                  <Bar dataKey="avg_ghi" fill="#fbbf24" name="Avg GHI (W/m²)" />
                  <Bar dataKey="avg_temp" fill="#3b82f6" name="Avg Temp (°C)" />
                </BarChart>
              </ResponsiveContainer>
            </SectionCard>
          )}

          {data.scatter.length > 0 && (
            <SectionCard title="GHI vs Temperature" sub="Scatter sample from recent points">
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis type="number" dataKey="ghi" name="GHI" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <YAxis type="number" dataKey="temp" name="Temp" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<ChartTooltip />} />
                  <Scatter data={data.scatter} fill="#22d3ee" name="Points" />
                </ScatterChart>
              </ResponsiveContainer>
            </SectionCard>
          )}

          {data.timeseries && data.timeseries.length > 0 && (
            <>
              {/* Power vs GHI Correlation */}
              {data.timeseries.some((p) => p.power_avg_w && p.ghi_w_m2) && (
                <SectionCard title="Power Generation vs Solar Input" sub="Normalized power vs GHI (Global Horizontal Irradiance)">
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart data={data.timeseries.slice(-250)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="timestamp_utc" hide />
                      <YAxis yAxisId="power" tick={{ fill: "#71717a", fontSize: 10 }} />
                      <YAxis yAxisId="ghi" orientation="right" tick={{ fill: "#71717a", fontSize: 10 }} />
                      <Tooltip content={<ChartTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />
                      <Line yAxisId="power" type="monotone" dataKey="power_avg_w" stroke="#10b981" name="Power (W)" dot={false} strokeWidth={2} />
                      <Line yAxisId="ghi" type="monotone" dataKey="ghi_w_m2" stroke="#fbbf24" name="GHI (W/m²)" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </SectionCard>
              )}

              {/* Irradiance Components */}
              {data.timeseries.some((p) => (p.ghi_w_m2 || p.ni_w_m2 || p.dhi_w_m2) && (p.ghi_w_m2 || p.ni_w_m2 || p.dhi_w_m2)) && (
                <SectionCard title="Irradiance Components" sub="Global, Direct Normal, and Diffuse Horizontal Irradiance">
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart data={data.timeseries.slice(-250)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="timestamp_utc" hide />
                      <YAxis tick={{ fill: "#71717a", fontSize: 10 }} />
                      <Tooltip content={<ChartTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />
                      {data.timeseries.some((p) => p.ghi_w_m2) && (
                        <Line type="monotone" dataKey="ghi_w_m2" stroke="#fbbf24" name="GHI (W/m²)" dot={false} strokeWidth={2} />
                      )}
                      {data.timeseries.some((p) => p.ni_w_m2) && (
                        <Line type="monotone" dataKey="ni_w_m2" stroke="#f97316" name="DNI (W/m²)" dot={false} />
                      )}
                      {data.timeseries.some((p) => p.dhi_w_m2) && (
                        <Line type="monotone" dataKey="dhi_w_m2" stroke="#8b5cf6" name="DHI (W/m²)" dot={false} />
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </SectionCard>
              )}

              {/* Environmental Conditions */}
              {data.timeseries.some((p) => p.ambient_temp_c || p.relative_humidity_pct || p.wind_speed_m_s) && (
                <SectionCard title="Environmental Conditions" sub="Temperature, humidity, and wind speed trends">
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart data={data.timeseries.slice(-250)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="timestamp_utc" hide />
                      <YAxis yAxisId="temp" tick={{ fill: "#71717a", fontSize: 10 }} />
                      <YAxis yAxisId="humidity" orientation="right" tick={{ fill: "#71717a", fontSize: 10 }} />
                      <Tooltip content={<ChartTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />
                      {data.timeseries.some((p) => p.ambient_temp_c) && (
                        <Line yAxisId="temp" type="monotone" dataKey="ambient_temp_c" stroke="#ef4444" name="Temp (°C)" dot={false} strokeWidth={2} />
                      )}
                      {data.timeseries.some((p) => p.relative_humidity_pct) && (
                        <Line yAxisId="humidity" type="monotone" dataKey="relative_humidity_pct" stroke="#22d3ee" name="Humidity (%)" dot={false} />
                      )}
                      {data.timeseries.some((p) => p.wind_speed_m_s) && (
                        <Line yAxisId="humidity" type="monotone" dataKey="wind_speed_m_s" stroke="#06b6d4" name="Wind (m/s)" dot={false} strokeDasharray="5 5" />
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </SectionCard>
              )}

              {/* All Numeric Columns Overview */}
              {data.all_columns && data.all_columns.length > 3 && (
                <SectionCard title="Multi-Column Overview" sub={`Available metrics: ${data.all_columns.join(", ")}`}>
                  <p className="text-xs text-s2-muted mb-3">
                    {data.timeseries.length} data points loaded. Each chart displays the last 250 observations.
                  </p>
                </SectionCard>
              )}
            </>
          )}

          {(data.recent.length > 0 || (data.timeseries && data.timeseries.length > 0)) && (
            <SectionCard title="Recent Timeline" sub="Latest observations from file">
              <ResponsiveContainer width="100%" height={300}>
                <LineChart
                  data={data.recent.map((p) => ({
                    ...p,
                    tsLabel: new Date(p.timestamp_utc).toLocaleString(),
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="tsLabel" hide />
                  <YAxis yAxisId="ghi" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <YAxis yAxisId="temp" orientation="right" tick={{ fill: "#71717a", fontSize: 10 }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />
                  <Line yAxisId="ghi" type="monotone" dataKey="ghi" stroke="#fbbf24" dot={false} name="GHI (W/m²)" />
                  <Line yAxisId="temp" type="monotone" dataKey="temp" stroke="#ef4444" dot={false} name="Temp (°C)" />
                </LineChart>
              </ResponsiveContainer>

              <div className="mt-3">
                <DataTable
                  title="Recent Parsed Rows"
                  columns={allIngestedColumns}
                  rows={allIngestedRows}
                />
              </div>
            </SectionCard>
          )}

          {data.total_points === 0 && (
            <div className="rounded-lg bg-[#1f1f14] border border-[#7f7f14] p-3 text-xs text-s2-muted text-center">
              No data parsed from file. Please check the file format and required columns.
            </div>
          )}
        </>
      )}
    </div>
  );
}
