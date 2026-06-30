import { useState, useEffect } from "react";
import type { DatasetInfo } from "../api";
import { fetchDatasets, fetchHealth, switchDataset } from "../api";

interface Props {
  currentDatasetId: string | null;
  currentDatasetName: string | null;
  onSwitch: (datasetId: string, datasetName: string) => void;
}

export default function DatasetSelector({ currentDatasetId, currentDatasetName, onSwitch }: Props) {
  const [open, setOpen] = useState(false);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [useCaseMode, setUseCaseMode] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setListLoading(true);
    fetchDatasets()
      .then((data) => {
        setDatasets(data.datasets);
        setUseCaseMode(data.use_case_mode);
      })
      .catch(() => setError("Failed to load datasets."))
      .finally(() => setListLoading(false));
  }, [open]);

  async function handleLoad() {
    if (!selectedId) return;
    setLoading(true);
    setError("");
    const selectedName = datasets.find((d) => d.id === selectedId)?.name ?? selectedId;
    try {
      const res = await switchDataset(selectedId, displayName || undefined);
      if (res.status === "ready") {
        onSwitch(res.dataset_id, res.dataset_name ?? selectedName);
        setOpen(false);
        setSelectedId(null);
        setDisplayName("");
        setSearch("");
      } else {
        // Batch prediction running — poll health until ready
        setScoring(true);
        while (true) {
          await new Promise((r) => setTimeout(r, 5000));
          try {
            const h = await fetchHealth();
            if (h.status === "ok") {
              onSwitch(selectedId, displayName || selectedName);
              setOpen(false);
              setSelectedId(null);
              setDisplayName("");
              setSearch("");
              break;
            }
            if (h.status === "error") {
              setError(h.detail ?? "Scoring failed — check application logs.");
              break;
            }
          } catch { /* network blip — keep polling */ }
        }
        setScoring(false);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const filtered = datasets.filter((d) =>
    d.name.toLowerCase().includes(search.toLowerCase()) ||
    d.id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={wrapStyle}>
      {/* Always-visible badge */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={eyebrowStyle}>SCORING DATASET</div>
          <div style={datasetNameStyle} title={currentDatasetId ?? undefined}>
            {currentDatasetName ?? currentDatasetId ?? "—"}
          </div>
          {currentDatasetId && (
            <div style={idStyle}>{currentDatasetId}</div>
          )}
        </div>
        <button onClick={() => setOpen((o) => !o)} style={changeBtnStyle}>
          {open ? "Cancel" : "Change"}
        </button>
      </div>

      {/* Dropdown panel */}
      {open && (
        <div style={panelStyle}>
          {useCaseMode && (
            <div style={noticeStyle}>Showing datasets from configured use case</div>
          )}

          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search datasets…"
            style={searchStyle}
            autoFocus
          />

          {listLoading ? (
            <div style={mutedStyle}>Loading…</div>
          ) : filtered.length === 0 ? (
            <div style={mutedStyle}>No datasets found.</div>
          ) : (
            <div style={listStyle}>
              {filtered.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedId(d.id === selectedId ? null : d.id)}
                  style={{
                    ...listItemStyle,
                    ...(selectedId === d.id ? listItemActiveStyle : {}),
                    ...(d.id === currentDatasetId ? listItemCurrentStyle : {}),
                  }}
                >
                  <div style={{ fontWeight: selectedId === d.id ? 500 : 400 }}>{d.name}</div>
                  <div style={idStyle}>{d.id}</div>
                  {d.id === currentDatasetId && (
                    <div style={{ fontSize: 9, fontFamily: "'Fragment Mono', monospace", textTransform: "uppercase", color: "#81FBA5", marginTop: 2 }}>
                      Active
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}

          {selectedId && selectedId !== currentDatasetId && (
            <div style={{ marginTop: 10 }}>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={`Display name (default: dataset name)`}
                style={{ ...searchStyle, marginBottom: 8 }}
              />
              {error && <div style={{ color: "#c0392b", fontSize: 11, marginBottom: 6 }}>{error}</div>}
              <button onClick={handleLoad} disabled={loading || scoring} style={loadBtnStyle}>
                {scoring ? "Scoring dataset — this may take a few minutes…" : loading ? "Loading…" : "Load selected dataset"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const wrapStyle: React.CSSProperties = {
  borderBottom: "1px solid #E4E4E4",
  paddingBottom: 14,
  marginBottom: 14,
};
const eyebrowStyle: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "#5C41FF",
  marginBottom: 4,
};
const datasetNameStyle: React.CSSProperties = {
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 13,
  fontWeight: 500,
  color: "#0B0B0B",
  wordBreak: "break-all",
  lineHeight: 1.3,
};
const idStyle: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  color: "#6C6A6B",
  marginTop: 2,
  wordBreak: "break-all",
};
const changeBtnStyle: React.CSSProperties = {
  flexShrink: 0,
  background: "none",
  border: "none",
  cursor: "pointer",
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 12,
  color: "#5C41FF",
  padding: "0 0 0 8px",
  fontWeight: 500,
};
const panelStyle: React.CSSProperties = {
  marginTop: 10,
  background: "#F5F5F5",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  padding: 10,
};
const noticeStyle: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "#6C6A6B",
  marginBottom: 8,
};
const searchStyle: React.CSSProperties = {
  width: "100%",
  padding: "5px 8px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  fontSize: 12,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  outline: "none",
  boxSizing: "border-box",
};
const listStyle: React.CSSProperties = {
  maxHeight: 200,
  overflowY: "auto",
  marginTop: 6,
  display: "flex",
  flexDirection: "column",
  gap: 2,
};
const listItemStyle: React.CSSProperties = {
  textAlign: "left",
  background: "#FFFFFF",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  padding: "6px 8px",
  cursor: "pointer",
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 12,
  color: "#0B0B0B",
  width: "100%",
};
const listItemActiveStyle: React.CSSProperties = {
  borderColor: "#5C41FF",
  background: "#F0EDFF",
};
const listItemCurrentStyle: React.CSSProperties = {
  borderColor: "#81FBA5",
  background: "#F0FFF5",
};
const loadBtnStyle: React.CSSProperties = {
  width: "100%",
  padding: "7px 12px",
  background: "#5C41FF",
  color: "#FFFFFF",
  border: "none",
  borderRadius: 2,
  cursor: "pointer",
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 13,
  fontWeight: 500,
};
const mutedStyle: React.CSSProperties = {
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 12,
  color: "#6C6A6B",
  padding: "8px 0",
};
