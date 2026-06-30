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
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        try {
          const cfg = await fetchAppConfig();
          if (!cancelled) setAppConfig(cfg);
          return;
        } catch {
          if (!cancelled) await new Promise((r) => setTimeout(r, 4000));
        }
      }
    };
    poll();
    return () => { cancelled = true; };
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
          <DrLogo height={28} />
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

function DrLogo({ height }: { height: number }) {
  const w = Math.round(height * (500 / 76));
  return (
    <svg width={w} height={height} viewBox="0 0 500 76" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path fillRule="evenodd" clipRule="evenodd" d="M320.142 67.1472L306.38 42.2558V42.246H306.389L306.282 42.0503H293.958V67.1374H285.511V8.37895H309.708C315.845 8.37895 320.582 9.87654 324.174 12.9598C327.747 16.0333 329.48 19.9192 329.48 24.8329C329.48 32.8983 324.312 39.0551 315.649 41.3064L315.179 41.4336L329.901 67.1472H320.142ZM309.13 15.632H293.958V34.8266H309.13C317.058 34.8266 321.072 31.6552 321.072 25.2636C321.072 18.8719 317.058 15.632 309.13 15.632ZM418.69 62.3117C414.971 66.2942 410.226 68.3106 404.6 68.3118C398.807 68.3104 393.455 65.5406 390.637 61.0881L389.952 60.0017V67.1079H382.033V8.38859H389.952V32.9765L390.637 31.9292C393.671 27.2896 399.055 24.5195 405.035 24.5195C410.605 24.5195 415.107 26.5065 418.778 30.598C422.497 34.572 424.377 39.975 424.377 46.4157C424.377 52.8563 422.468 58.2006 418.69 62.3117ZM393.319 35.9815C390.716 38.6624 389.395 42.1845 389.394 46.4304C389.395 50.6568 390.716 54.1983 393.319 56.9673C395.961 59.6982 399.113 61.0784 402.843 61.0784C406.572 61.0784 409.88 59.6591 412.396 56.9673C415.029 54.1581 416.311 50.7029 416.311 46.4352C416.311 42.1676 414.99 38.6536 412.396 35.9913C409.87 33.2016 406.621 31.7823 402.843 31.7823C399.064 31.7823 395.952 33.1625 393.319 35.9815ZM494.122 68.3509C496.322 68.3505 498.298 68.0471 500 67.4504L499.315 60.863C498.287 61.137 497.386 61.2643 496.496 61.2643C492.404 61.2643 490.339 59.0522 490.339 54.6964V31.9683H499.765V25.7528H490.339V14.3593H482.42V25.7528H475.608V31.9878H482.42V56.2429C482.42 64.385 486.246 68.3493 494.122 68.3509ZM467.846 30.6368C463.637 26.5649 457.911 24.3234 452.155 24.5094C446.194 24.5094 440.958 26.4866 436.573 30.3725C432.129 34.2975 429.975 39.544 429.975 46.4251C429.975 53.3062 431.933 58.0339 435.956 61.9002V61.8806L436.573 62.4288C440.958 66.3245 446.194 68.2919 452.136 68.2919C457.93 68.4681 463.637 66.2462 467.836 62.1645C470.782 59.3063 474.296 54.2556 474.296 46.3957C474.296 38.5358 470.782 33.4753 467.836 30.627L467.846 30.6368ZM462.1 56.9768C459.369 59.6979 455.983 61.078 452.048 61.078C448.113 61.078 444.824 59.6979 442.093 56.9768C439.431 54.3144 438.08 50.7613 438.08 46.4349C438.08 42.1085 439.431 38.5456 442.093 35.893C444.824 33.1719 448.181 31.7918 452.048 31.7918C455.914 31.7918 459.36 33.1719 462.1 35.893C464.821 38.6141 466.202 42.1672 466.202 46.4349C466.202 50.7025 464.821 54.2654 462.1 56.9768ZM369.964 30.6368C365.755 26.5649 360.029 24.3234 354.273 24.5094C348.312 24.5094 343.076 26.4866 338.691 30.3725C334.247 34.2975 332.093 39.544 332.093 46.4251C332.093 53.3062 334.051 58.0339 338.074 61.9002V61.8806L338.691 62.4288C343.076 66.3245 348.312 68.2919 354.254 68.2919C360.058 68.4681 365.755 66.2462 369.954 62.1645C372.9 59.3063 376.414 54.2556 376.414 46.3957C376.414 38.5358 372.9 33.4753 369.954 30.627L369.964 30.6368ZM364.228 56.9768C361.497 59.6979 358.11 61.078 354.175 61.078C350.241 61.078 346.952 59.6979 344.221 56.9768C341.558 54.3144 340.208 50.7613 340.208 46.4349C340.208 42.1085 341.558 38.5456 344.221 35.893C346.952 33.1719 350.309 31.7918 354.175 31.7918C358.042 31.7918 361.487 33.1719 364.228 35.893C366.949 38.6141 368.329 42.1672 368.329 46.4349C368.329 50.7025 366.949 54.2556 364.228 56.9768ZM258.388 24.5683H257.507C252.848 24.6955 249.168 25.8505 246.29 28.1018C243.677 30.1573 242.218 32.4967 241.846 35.2569C241.846 35.2569 241.641 36.9111 241.611 37.7921H249.031C249.041 36.872 249.373 35.2667 249.373 35.2667C249.931 32.1639 253.347 30.2454 258.388 30.2454C264.418 30.2454 267.599 32.9078 267.599 37.9291V40.0434L253.944 42.2163C244.695 43.6552 239.389 48.5689 239.389 55.7045C239.389 63.2609 245.018 68.341 253.387 68.341C259.739 68.341 264.34 65.522 267.07 59.9721L267.775 58.5332V67.1566H275.527L275.537 38.4773C275.537 29.384 269.615 24.5683 258.398 24.5683H258.388ZM267.609 47.453C267.54 55.9394 262.274 61.8514 254.747 61.8514C250.313 61.8514 247.328 59.1793 247.328 55.1955C247.328 51.2117 250.176 48.6668 255.804 47.6879L267.638 45.652L267.609 47.453ZM234.995 67.4504C233.293 68.0471 231.318 68.3505 229.117 68.3509C221.241 68.3493 217.415 64.385 217.415 56.2429V31.9878H210.603V25.7528H217.415V14.3593H225.334V25.7528H234.76V31.9683H225.334V54.6964C225.334 59.0522 227.399 61.2643 231.491 61.2643C232.382 61.2643 233.282 61.137 234.31 60.863L234.995 67.4504ZM189.303 24.5683H188.422C183.763 24.6955 180.082 25.8505 177.205 28.1018C174.591 30.1573 173.133 32.4967 172.761 35.2569C172.761 35.2569 172.555 36.9111 172.526 37.7921H179.945C179.955 36.872 180.288 35.2667 180.288 35.2667C180.846 32.1639 184.262 30.2454 189.303 30.2454C195.332 30.2454 198.514 32.9078 198.514 37.9291V40.0434L184.859 42.2163C175.609 43.6552 170.304 48.5689 170.304 55.7045C170.304 63.2609 175.932 68.341 184.301 68.341C190.654 68.341 195.254 65.522 197.985 59.9721L198.69 58.5332V67.1566H206.442L206.452 38.4773C206.452 29.384 200.53 24.5683 189.313 24.5683H189.303ZM198.523 47.453C198.455 55.9394 193.189 61.8514 185.662 61.8514C181.228 61.8514 178.242 59.1793 178.242 55.1955C178.242 51.2117 181.091 48.6668 186.719 47.6879L198.553 45.652L198.523 47.453ZM165.969 37.7731C165.969 47.1208 163.091 54.4326 157.424 59.4931V59.5028C151.707 64.6318 144.356 67.1278 134.96 67.1278H118.153V8.39876H134.96C144.141 8.39876 151.697 10.9926 157.424 16.1118C163.179 21.2702 165.969 28.4254 165.969 37.7731ZM135.126 15.9846H126.581V59.5812H135.498V59.5616C149.397 59.4147 157.355 51.6234 157.355 37.7731C157.355 23.9228 149.25 15.9846 135.126 15.9846Z" fill="#FFFFFF"/>
      <path fillRule="evenodd" clipRule="evenodd" d="M0 0H39.1527V8.38847H0V0ZM58.7288 8.38859H39.1524V16.7771H58.7288V8.38859ZM0 16.7772H39.1527V25.1656H0V16.7772ZM78.3056 25.1749H58.7292V33.5633H78.3056V25.1749ZM0 33.564H58.7291V41.9524H0V33.564ZM78.3056 41.9526H58.7292V50.341H78.3056V41.9526ZM0 50.3406H39.1527V58.7291H0V50.3406ZM58.7288 58.7292H39.1524V67.1177H58.7288V58.7292ZM39.1527 67.1178H0V75.5062H39.1527V67.1178Z" fill="#81FBA5"/>
    </svg>
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
