// -------------------------------------------------------------------------
// TabNav.jsx — Top-level tab navigation between the three views.
// -------------------------------------------------------------------------

const TABS = [
  { id: "controller", label: "Live Controller" },
  { id: "ghi", label: "GHI Analysis" },
  { id: "dataset", label: "Drive Dataset" },
  { id: "analytics", label: "Comparative Analytics" },
  { id: "diagnostics", label: "ML Diagnostics" },
];

export default function TabNav({ activeTab, onTabChange }) {
  return (
    <nav className="flex gap-1 rounded-lg bg-s2-card border border-s2-border p-1">
      {TABS.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`px-4 py-2 rounded-md text-xs font-semibold tracking-wide transition-colors
              ${active
                ? "bg-s2-blue text-white"
                : "text-s2-muted hover:text-s2-text hover:bg-[#1e1e22]"
              }`}
          >
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
