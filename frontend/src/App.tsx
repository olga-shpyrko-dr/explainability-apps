import { useState, useEffect, useCallback } from "react";
import type { CohortProfile, GroupStat, RowExplanation } from "./api";
import { fetchCohort, fetchGroups, fetchRow } from "./api";
import CohortFilter from "./components/CohortFilter";
import GroupExplanationChart from "./components/GroupExplanationChart";
import WaterfallChart from "./components/WaterfallChart";
import NarrativePanel from "./components/NarrativePanel";
import ScoreHistogram from "./components/ScoreHistogram";

type Tab = "groups" | "row" | "narrative";

function App() {
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [profile, setProfile] = useState<CohortProfile | null>(null);
  const [groups, setGroups] = useState<GroupStat[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [tab, setTab] = useState<Tab>("groups");
  const [rowId, setRowId] = useState("");
  const [rowData, setRowData] = useState<RowExplanation | null>(null);
  const [rowLoading, setRowLoading] = useState(false);
  const [rowError, setRowError] = useState("");

  const refresh = useCallback(async () => {
    setProfileLoading(true);
    setGroupsLoading(true);
    try {
      const [p, g] = await Promise.all([fetchCohort(filters), fetchGroups(filters)]);
      setProfile(p);
      setGroups(g.groups);
    } finally {
      setProfileLoading(false);
      setGroupsLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    const t = setTimeout(refresh, 400);
    return () => clearTimeout(t);
  }, [refresh]);

  async function lookupRow() {
    if (!rowId.trim()) return;
    setRowLoading(true);
    setRowError("");
    setRowData(null);
    try {
      const r = await fetchRow(rowId.trim());
      setRowData(r);
    } catch {
      setRowError(`Policy "${rowId}" not found.`);
    } finally {
      setRowLoading(false);
    }
  }

  return (
    <div style={appStyle}>
      <header style={headerStyle}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
            Protection Lapse Propensity — Explainability
          </h1>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "#bbb" }}>
            Model 6a22f2ab · Under-55 cohort, excl. UL
          </p>
        </div>
      </header>

      <div style={bodyStyle}>
        <aside style={sidebarStyle}>
          <CohortFilter filters={filters} onChange={setFilters} />
        </aside>

        <main style={mainStyle}>
          <div style={summaryBarStyle}>
            {profileLoading ? (
              <span style={{ color: "#888" }}>Loading…</span>
            ) : profile ? (
              <>
                <Stat label="Cohort size" value={`${profile.n_rows.toLocaleString()} policies`} />
                <Stat label="% of total" value={`${profile.pct_of_total.toFixed(1)}%`} />
                <Stat
                  label="Mean score"
                  value={profile.score_stats.mean != null ? (profile.score_stats.mean * 100).toFixed(1) + "%" : "—"}
                />
                <Stat
                  label="Median score"
                  value={profile.score_stats.median != null ? (profile.score_stats.median * 100).toFixed(1) + "%" : "—"}
                />
                <Stat
                  label="Population mean"
                  value={profile.score_stats_full.mean != null ? (profile.score_stats_full.mean * 100).toFixed(1) + "%" : "—"}
                />
              </>
            ) : null}
          </div>

          {profile && profile.score_histogram.length > 0 && (
            <div style={cardStyle}>
              <h3 style={cardTitle}>Score distribution (cohort)</h3>
              <ScoreHistogram data={profile.score_histogram} />
            </div>
          )}

          <div style={tabBarStyle}>
            {(["groups", "row", "narrative"] as Tab[]).map((t) => (
              <button key={t} onClick={() => setTab(t)} style={{ ...tabBtn, ...(tab === t ? tabBtnActive : {}) }}>
                {t === "groups" ? "Group Explanations" : t === "row" ? "Individual Policy" : "AI Narrative"}
              </button>
            ))}
          </div>

          {tab === "groups" && (
            <div style={cardStyle}>
              <h3 style={cardTitle}>Group SHAP contributions</h3>
              <GroupExplanationChart groups={groups} loading={groupsLoading} />
            </div>
          )}

          {tab === "row" && (
            <div style={cardStyle}>
              <h3 style={cardTitle}>Individual policy explanation</h3>
              <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
                <input
                  value={rowId}
                  onChange={(e) => setRowId(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && lookupRow()}
                  placeholder="Enter Policy Number…"
                  style={searchInput}
                />
                <button onClick={lookupRow} style={primaryBtn}>Look up</button>
              </div>
              {rowError && <p style={{ color: "red", fontSize: 13 }}>{rowError}</p>}
              {rowData && (
                <WaterfallChart
                  rowId={rowData.row_id}
                  prediction={rowData.prediction}
                  waterfall={rowData.waterfall}
                  loading={rowLoading}
                />
              )}
            </div>
          )}

          {tab === "narrative" && (
            <div style={cardStyle}>
              <h3 style={cardTitle}>AI narrative summary</h3>
              <NarrativePanel filters={filters} nRows={profile?.n_rows ?? 0} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 11, color: "#888" }}>{label}</div>
    </div>
  );
}

const appStyle: React.CSSProperties = { fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#f5f5f5" };
const headerStyle: React.CSSProperties = { background: "#0B0B0B", color: "#fff", padding: "14px 24px", display: "flex", alignItems: "center" };
const bodyStyle: React.CSSProperties = { display: "flex", minHeight: "calc(100vh - 60px)" };
const sidebarStyle: React.CSSProperties = { width: 260, background: "#fff", borderRight: "1px solid #e0e0e0", padding: 16, overflowY: "auto", flexShrink: 0 };
const mainStyle: React.CSSProperties = { flex: 1, padding: 20, overflowY: "auto" };
const summaryBarStyle: React.CSSProperties = { background: "#fff", border: "1px solid #e0e0e0", borderRadius: 8, padding: "12px 24px", display: "flex", gap: 32, marginBottom: 16, flexWrap: "wrap" };
const cardStyle: React.CSSProperties = { background: "#fff", border: "1px solid #e0e0e0", borderRadius: 8, padding: 20, marginBottom: 16 };
const cardTitle: React.CSSProperties = { margin: "0 0 12px", fontSize: 15, fontWeight: 600 };
const tabBarStyle: React.CSSProperties = { display: "flex", gap: 4, marginBottom: 16 };
const tabBtn: React.CSSProperties = { padding: "8px 16px", border: "1px solid #ddd", borderRadius: 6, cursor: "pointer", background: "#fff", fontSize: 13, color: "#333" };
const tabBtnActive: React.CSSProperties = { background: "#0B0B0B", color: "#81FBA5", borderColor: "#0B0B0B" };
const searchInput: React.CSSProperties = { flex: 1, padding: "6px 10px", border: "1px solid #ddd", borderRadius: 4, fontSize: 13 };
const primaryBtn: React.CSSProperties = { padding: "6px 16px", background: "#5C41FF", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 13 };

export default App;
