import { useState, useEffect, useCallback } from "react";
import type { AppConfig, CohortProfile, GroupStat, RowExplanation } from "./api";
import { fetchAppConfig, fetchCohort, fetchGroups, fetchRow } from "./api";
import CohortFilter from "./components/CohortFilter";
import DatasetSelector from "./components/DatasetSelector";
import GroupExplanationChart from "./components/GroupExplanationChart";
import InlineNarrative from "./components/InlineNarrative";
import WaterfallChart from "./components/WaterfallChart";
import ScoreHistogram from "./components/ScoreHistogram";

type Tab = "groups" | "row";

const C = {
  green:  "#81FBA5",
  black:  "#0B0B0B",
  grey:   "#E4E4E4",
  white:  "#FFFFFF",
  purple: "#909BF5",
  indigo: "#5C41FF",
  muted:  "#6C6A6B",
  bg:     "#F5F5F5",
};

function App() {
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null);
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

  useEffect(() => {
    fetchAppConfig()
      .then(setAppConfig)
      .catch((e) => console.error("Failed to load /api/config:", e));
  }, []);

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

  async function lookupRow(id?: string) {
    const target = (id ?? rowId).trim();
    if (!target) return;
    if (id) setRowId(id);
    setTab("row");
    setRowLoading(true);
    setRowError("");
    setRowData(null);
    try {
      const r = await fetchRow(target);
      setRowData(r);
    } catch {
      setRowError(`"${target}" not found.`);
    } finally {
      setRowLoading(false);
    }
  }

  // After a dataset switch: update config state with new dataset info, reset filters and data
  const handleDatasetSwitch = useCallback((datasetId: string, datasetName: string) => {
    setAppConfig((prev) =>
      prev ? { ...prev, current_dataset_id: datasetId, current_dataset_name: datasetName } : prev
    );
    setFilters({});
    setProfile(null);
    setGroups([]);
    setRowData(null);
    setRowId("");
  }, []);

  const entityLabel = appConfig?.entity_label ?? "row";
  const entityLabelPlural = appConfig?.entity_label_plural ?? "rows";
  const title = appConfig?.app_title ?? "Prediction Explainability";
  const subtitle = appConfig?.app_subtitle ?? "";

  const TABS: { id: Tab; label: string }[] = [
    { id: "groups", label: "Group Explanations" },
    { id: "row",    label: `Individual ${entityLabel.charAt(0).toUpperCase() + entityLabel.slice(1)}` },
  ];

  return (
    <div style={{ fontFamily: "'DM Sans', system-ui, sans-serif", minHeight: "100vh", background: C.bg }}>

      {/* Brand bar — 4 px green stripe */}
      <div style={{ height: 4, background: C.green }} />

      {/* Header */}
      <header style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <img src="/datarobot-logo.svg" alt="DataRobot" style={{ height: 28 }} />
          <div style={{ width: 1, height: 28, background: "#3a3a3a" }} />
          <div>
            <div style={{ fontSize: 15, fontWeight: 500, color: C.white, lineHeight: 1.2 }}>{title}</div>
            {subtitle && (
              <div style={{ fontSize: 10, color: C.green, fontFamily: "'Fragment Mono', monospace", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 2 }}>
                {subtitle}
              </div>
            )}
          </div>
        </div>
      </header>

      <div style={{ display: "flex", minHeight: "calc(100vh - 56px)" }}>

        {/* Sidebar */}
        <aside style={sidebarStyle}>
          {appConfig?.dataset_selector_enabled && (
            <DatasetSelector
              currentDatasetId={appConfig.current_dataset_id}
              currentDatasetName={appConfig.current_dataset_name}
              onSwitch={handleDatasetSwitch}
            />
          )}
          <CohortFilter appConfig={appConfig} filters={filters} onChange={setFilters} />
        </aside>

        {/* Main content */}
        <main style={{ flex: 1, padding: 20, overflowY: "auto", minWidth: 0 }}>

          {/* Summary bar */}
          <div style={summaryBarStyle}>
            {profileLoading ? (
              <span style={{ color: C.muted, fontSize: 13 }}>Loading…</span>
            ) : profile ? (
              <>
                <StatCard label="COHORT SIZE" value={`${profile.n_rows.toLocaleString()} ${entityLabelPlural}`} accent />
                <StatCard label="% OF TOTAL"  value={`${profile.pct_of_total.toFixed(1)}%`} />
                <StatCard label="MEAN SCORE"  value={profile.score_stats.mean != null ? (profile.score_stats.mean * 100).toFixed(1) + "%" : "—"} />
                <StatCard label="MEDIAN SCORE" value={profile.score_stats.median != null ? (profile.score_stats.median * 100).toFixed(1) + "%" : "—"} />
                <StatCard label="POPULATION MEAN" value={profile.score_stats_full.mean != null ? (profile.score_stats_full.mean * 100).toFixed(1) + "%" : "—"} />
              </>
            ) : null}
          </div>

          {/* Score histogram */}
          {profile && profile.score_histogram.length > 0 && (
            <div style={cardStyle}>
              <div style={cardEyebrow}>SCORE DISTRIBUTION</div>
              <ScoreHistogram data={profile.score_histogram} />
            </div>
          )}

          {/* Tab bar */}
          <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
            {TABS.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{ ...tabBtn, ...(tab === t.id ? tabBtnActive : {}) }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* Group explanations */}
          {tab === "groups" && (
            <div style={cardStyle}>
              <div style={cardEyebrow}>GROUP SHAP CONTRIBUTIONS</div>
              <GroupExplanationChart
                groups={groups}
                loading={groupsLoading}
                factorPositiveLabel={appConfig?.factor_positive_label ?? "increases risk"}
                factorNegativeLabel={appConfig?.factor_negative_label ?? "reduces risk"}
                maxExplanations={appConfig?.max_explanations ?? 4}
              />
              <InlineNarrative mode="group" filters={filters} nRows={profile?.n_rows ?? 0} />
            </div>
          )}

          {/* Individual row */}
          {tab === "row" && (
            <div style={cardStyle}>
              <div style={cardEyebrow}>INDIVIDUAL {entityLabel.toUpperCase()} EXPLANATION</div>
              <div style={{ display: "flex", gap: 8, marginBottom: 16, marginTop: 12 }}>
                <input
                  value={rowId}
                  onChange={(e) => setRowId(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && lookupRow()}
                  placeholder={`Enter ${appConfig?.row_id_col ?? "ID"}…`}
                  style={inputStyle}
                />
                <button onClick={() => lookupRow()} style={primaryBtn}>Look up</button>
              </div>
              {profile?.sample_row_ids && profile.sample_row_ids.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontFamily: "'Fragment Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", color: "#6C6A6B", marginBottom: 6 }}>
                    Highest-scoring {entityLabelPlural} in cohort
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {profile.sample_row_ids.map((id) => (
                      <button key={id} onClick={() => lookupRow(id)} style={sampleRowBtn}>
                        {id}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {rowError && <p style={{ color: "#c0392b", fontSize: 13, margin: "0 0 8px" }}>{rowError}</p>}
              {rowData && (
                <>
                  <WaterfallChart
                    rowId={rowData.row_id}
                    prediction={rowData.prediction}
                    waterfall={rowData.waterfall}
                    loading={rowLoading}
                    highScoreLabel={appConfig?.high_score_label ?? "high risk"}
                    lowScoreLabel={appConfig?.low_score_label ?? "low risk"}
                    populationMean={profile?.score_stats_full.mean ?? null}
                    factorPositiveLabel={appConfig?.factor_positive_label ?? "increases risk"}
                    factorNegativeLabel={appConfig?.factor_negative_label ?? "reduces risk"}
                  />
                  <InlineNarrative mode="row" rowId={rowData.row_id} nRows={1} />
                </>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ textAlign: "center", padding: "0 4px" }}>
      <div style={{ fontSize: 18, fontWeight: 500, color: accent ? "#5C41FF" : "#0B0B0B" }}>{value}</div>
      <div style={{ fontSize: 9, fontFamily: "'Fragment Mono', monospace", textTransform: "uppercase", letterSpacing: "0.06em", color: "#6C6A6B", marginTop: 2 }}>{label}</div>
    </div>
  );
}

const headerStyle: React.CSSProperties = {
  background: "#0B0B0B",
  color: "#FFFFFF",
  padding: "12px 24px",
  display: "flex",
  alignItems: "center",
  height: 52,
};
const sidebarStyle: React.CSSProperties = {
  width: 264,
  background: "#FFFFFF",
  borderRight: "1px solid #E4E4E4",
  padding: 16,
  overflowY: "auto",
  flexShrink: 0,
};
const summaryBarStyle: React.CSSProperties = {
  background: "#FFFFFF",
  border: "1px solid #E4E4E4",
  borderRadius: 4,
  padding: "14px 24px",
  display: "flex",
  gap: 32,
  marginBottom: 16,
  flexWrap: "wrap",
  alignItems: "center",
};
const cardStyle: React.CSSProperties = {
  background: "#FFFFFF",
  border: "1px solid #E4E4E4",
  borderRadius: 4,
  padding: 20,
  marginBottom: 16,
};
const cardEyebrow: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "#6C6A6B",
  marginBottom: 12,
};
const tabBtn: React.CSSProperties = {
  padding: "8px 16px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  cursor: "pointer",
  background: "#FFFFFF",
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  color: "#0B0B0B",
};
const tabBtnActive: React.CSSProperties = {
  background: "#0B0B0B",
  color: "#81FBA5",
  borderColor: "#0B0B0B",
};
const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: "7px 10px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  outline: "none",
};
const primaryBtn: React.CSSProperties = {
  padding: "7px 18px",
  background: "#5C41FF",
  color: "#FFFFFF",
  border: "none",
  borderRadius: 2,
  cursor: "pointer",
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontWeight: 500,
};

const sampleRowBtn: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 11,
  padding: "4px 10px",
  cursor: "pointer",
  background: "#F5F5F5",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  color: "#0B0B0B",
};

export default App;
