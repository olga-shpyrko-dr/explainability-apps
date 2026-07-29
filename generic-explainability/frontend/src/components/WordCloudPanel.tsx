import { useEffect, useState } from "react";
import type { ColumnMeta } from "../api";
import { fetchWordCloud, withRetry, type WordFrequency } from "../api";
import WordCloud from "./WordCloud";

type View = "cloud" | "table";

interface Props {
  columns: ColumnMeta[];
  filters: Record<string, unknown>;
}

export default function WordCloudPanel({ columns, filters }: Props) {
  const textColumns = columns.filter((c) => c.type === "text");
  const [column, setColumn] = useState(textColumns[0]?.name ?? "");
  const [minFrequency, setMinFrequency] = useState(2);
  const [view, setView] = useState<View>("cloud");
  const [words, setWords] = useState<WordFrequency[]>([]);
  const [nRows, setNRows] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!column) return;
    const t = setTimeout(() => {
      setLoading(true);
      withRetry(() => fetchWordCloud(column, filters, minFrequency))
        .then((data) => {
          setWords(data.words);
          setNRows(data.n_rows);
        })
        .catch((e) => console.error("Failed to load /api/wordcloud:", e))
        .finally(() => setLoading(false));
    }, 400);
    return () => clearTimeout(t);
  }, [column, filters, minFrequency]);

  if (!textColumns.length) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 12 }}>
        {textColumns.length > 1 && (
          <div style={fieldStyle}>
            <label style={labelStyle}>Column</label>
            <select value={column} onChange={(e) => setColumn(e.target.value)} style={inputStyle}>
              {textColumns.map((c) => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>
          </div>
        )}
        <div style={fieldStyle}>
          <label style={labelStyle}>Min. frequency</label>
          <input
            type="number"
            min={1}
            value={minFrequency}
            onChange={(e) => setMinFrequency(Math.max(1, Number(e.target.value) || 1))}
            style={{ ...inputStyle, width: 72 }}
          />
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {(["cloud", "table"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} style={{ ...toggleBtn, ...(view === v ? toggleBtnActive : {}) }}>
              {v === "cloud" ? "Cloud" : "Table"}
            </button>
          ))}
        </div>
      </div>
      <span style={{ fontSize: 11, color: "#6C6A6B", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
        {nRows.toLocaleString()} rows
      </span>

      <div style={{ width: "100%" }}>
        {loading ? (
          <p style={{ fontSize: 13, color: "#6C6A6B", fontFamily: "'DM Sans', system-ui, sans-serif" }}>Loading…</p>
        ) : view === "cloud" ? (
          <WordCloud words={words} />
        ) : (
          <div style={{ maxHeight: 280, overflowY: "auto" }}>
            <table style={{ width: "100%", fontSize: 13, fontFamily: "'DM Sans', system-ui, sans-serif", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #E4E4E4", textAlign: "left" }}>
                  <th style={{ padding: "4px 12px 4px 0", fontWeight: 500 }}>Word</th>
                  <th style={{ padding: "4px 0", fontWeight: 500 }}>Count</th>
                </tr>
              </thead>
              <tbody>
                {words.map(({ word, count }) => (
                  <tr key={word} style={{ borderBottom: "1px solid #F5F5F5" }}>
                    <td style={{ padding: "4px 12px 4px 0" }}>{word}</td>
                    <td style={{ padding: "4px 0" }}>{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!words.length && (
              <p style={{ fontSize: 13, color: "#6C6A6B", fontFamily: "'DM Sans', system-ui, sans-serif", padding: "8px 0" }}>
                No words match the current filters.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const fieldStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4 };
const labelStyle: React.CSSProperties = {
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 12,
  fontWeight: 500,
  color: "#0B0B0B",
};
const inputStyle: React.CSSProperties = {
  padding: "5px 8px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  outline: "none",
};
const toggleBtn: React.CSSProperties = {
  padding: "5px 12px",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "#E4E4E4",
  borderRadius: 2,
  cursor: "pointer",
  background: "#FFFFFF",
  fontSize: 12,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  color: "#0B0B0B",
};
const toggleBtnActive: React.CSSProperties = {
  background: "#0B0B0B",
  color: "#81FBA5",
  borderColor: "#0B0B0B",
};
