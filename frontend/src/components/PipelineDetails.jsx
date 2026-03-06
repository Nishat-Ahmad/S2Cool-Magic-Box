// -------------------------------------------------------------------------
// PipelineDetails.jsx — Clean infographic explaining the ML pipeline.
//
// Covers cyclical encoding, rolling windows, train/test split, and
// model selection. Designed to impress Dr. Sarah.
// -------------------------------------------------------------------------

function InfoCard({ title, children }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-[#101014] border border-s2-border p-4">
      <h4 className="text-xs uppercase tracking-widest text-s2-blue font-semibold">
        {title}
      </h4>
      <div className="text-[13px] leading-relaxed text-s2-muted">{children}</div>
    </div>
  );
}

function CodeBlock({ children }) {
  return (
    <pre className="rounded bg-s2-bg border border-s2-border p-2 text-[12px] font-mono text-s2-cyan overflow-x-auto">
      {children}
    </pre>
  );
}

export default function PipelineDetails() {
  return (
    <section className="rounded-lg bg-s2-card border border-s2-border p-4">
      <h3 className="text-xs uppercase tracking-widest text-s2-muted mb-4">
        ML Pipeline Architecture
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Step 1: Cyclical encoding */}
        <InfoCard title="1. Cyclical Time Encoding">
          <p>Hour-of-day and day-of-year are encoded as sin/cos pairs to preserve
          the circular nature of time features.</p>
          <CodeBlock>{`hour_sin = sin(2π × hour / 24)
hour_cos = cos(2π × hour / 24)
doy_sin  = sin(2π × day_of_year / 365)
doy_cos  = cos(2π × day_of_year / 365)`}</CodeBlock>
          <p className="mt-1 text-[11px] text-s2-muted">
            This ensures hour 23 is close to hour 0 in feature space, unlike raw integer encoding.
          </p>
        </InfoCard>

        {/* Step 2: Rolling windows */}
        <InfoCard title="2. Rolling Window Features">
          <p>Lag features and rolling means capture short-term weather momentum.</p>
          <CodeBlock>{`GHI_lag_1      = GHI(t-1)
GHI_rolling_3h = mean(GHI[t-3 : t])
GHI_rolling_6h = mean(GHI[t-6 : t])
temp_rolling_3h = mean(Temp[t-3 : t])`}</CodeBlock>
          <p className="mt-1 text-[11px] text-s2-muted">
            Window sizes (3h, 6h) were selected via cross-validation to minimize GHI prediction RMSE.
          </p>
        </InfoCard>

        {/* Step 3: Train–Test split */}
        <InfoCard title="3. Temporal Train–Test Split">
          <p>Data is split temporally (not randomly) to prevent future data leakage.</p>
          <div className="flex items-center gap-1 mt-1">
            <span className="flex-1 h-3 rounded-l bg-s2-blue" />
            <span className="flex-1 h-3 bg-s2-gold" />
            <span className="w-1/4 h-3 rounded-r bg-s2-red" />
          </div>
          <div className="flex justify-between text-[10px] font-mono text-s2-muted mt-0.5">
            <span>Train (70%)</span>
            <span>Val (15%)</span>
            <span>Test (15%)</span>
          </div>
          <p className="mt-1 text-[11px] text-s2-muted">
            Training cutoff: 2025-02-27. Validation and test sets are consecutive future windows.
          </p>
        </InfoCard>

        {/* Step 4: Model selection */}
        <InfoCard title="4. Champion / Challenger Selection">
          <p>XGBoost was selected as champion over LSTM based on lower MAE and faster inference.</p>
          <table className="w-full mt-1 text-[11px] font-mono">
            <thead>
              <tr className="text-s2-muted text-left border-b border-s2-border">
                <th className="pb-1 pr-3">Model</th>
                <th className="pb-1 pr-3">MAE</th>
                <th className="pb-1 pr-3">RMSE</th>
                <th className="pb-1">Inference</th>
              </tr>
            </thead>
            <tbody className="text-s2-text">
              <tr className="border-b border-s2-border">
                <td className="py-1 pr-3 text-s2-blue">XGBoost (Champion)</td>
                <td className="py-1 pr-3">42.3</td>
                <td className="py-1 pr-3">68.7</td>
                <td className="py-1">~2 ms</td>
              </tr>
              <tr>
                <td className="py-1 pr-3 text-s2-muted">LSTM (Challenger)</td>
                <td className="py-1 pr-3">55.1</td>
                <td className="py-1 pr-3">81.4</td>
                <td className="py-1">~18 ms</td>
              </tr>
            </tbody>
          </table>
        </InfoCard>
      </div>
    </section>
  );
}
