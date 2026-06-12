import { useState, useEffect } from "react";
import type { ColumnMeta } from "../api";
import { fetchColumns } from "../api";

interface Props {
  filters: Record<string, unknown>;
  onChange: (filters: Record<string, unknown>) => void;
}

const DEMOGRAPHIC_COLS = ["Age_life1", "SmokerStatus", "Product_Desc", "MonthsSinceReview"];

// Prediction score columns to surface (from pre-scored dataset)
const SCORE_COL = "Lapse_ind_1_PREDICTION";
const DECILE_COL = "Decile";

// Explanation columns
const TOP_FEATURE_COL = "EXPLANATION_1_FEATURE_NAME";

export default function CohortFilter({ filters, onChange }: Props) {
  const [colMap, setColMap] = useState<Record<string, ColumnMeta>>({});

  useEffect(() => {
    fetchColumns().then((cols) => {
      const map: Record<string, ColumnMeta> = {};
      cols.forEach((c) => { map[c.name] = c; });
      setColMap(map);
    });
  }, []);

  function setFilter(col: string, value: unknown) {
    if (value === null || value === undefined || value === "") {
      const next = { ...filters };
      delete next[col];
      onChange(next);
    } else {
      onChange({ ...filters, [col]: value });
    }
  }

  function clearAll() { onChange({}); }

  const activeCount = Object.keys(filters).length;

  const topFeatureMeta = colMap[TOP_FEATURE_COL];
  const selectedFeatures = (filters[TOP_FEATURE_COL] as string[] | undefined) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Filters</h3>
        {activeCount > 0 && (
          <button onClick={clearAll} style={btnStyle}>
            Clear all ({activeCount})
          </button>
        )}
      </div>

      {/* ── Policyholder ── */}
      <div style={sectionLabel}>POLICYHOLDER</div>
      {DEMOGRAPHIC_COLS.map((name) => {
        const meta = colMap[name];
        if (!meta) return null;
        return (
          <FilterControl
            key={name}
            meta={meta}
            value={filters[name]}
            onChange={(v) => setFilter(name, v)}
          />
        );
      })}

      {/* ── Lapse score ── */}
      <div style={sectionLabel}>LAPSE SCORE</div>
      {[SCORE_COL, DECILE_COL].map((name) => {
        const meta = colMap[name];
        if (!meta) return null;
        return (
          <FilterControl
            key={name}
            meta={meta}
            value={filters[name]}
            onChange={(v) => setFilter(name, v)}
          />
        );
      })}

      {/* ── Top driver ── */}
      <div style={sectionLabel}>TOP DRIVER</div>

      {topFeatureMeta?.values && (
        <div style={fieldStyle}>
          <label style={labelStyle}>Top feature</label>
          <div style={{ maxHeight: 140, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
            {topFeatureMeta.values.map((v) => (
              <label key={v} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={selectedFeatures.includes(v)}
                  onChange={() => {
                    const next = selectedFeatures.includes(v)
                      ? selectedFeatures.filter((x) => x !== v)
                      : [...selectedFeatures, v];
                    setFilter(TOP_FEATURE_COL, next.length > 0 ? next : null);
                  }}
                />
                {v}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FilterControl({
  meta,
  value,
  onChange,
}: {
  meta: ColumnMeta;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const label = meta.name
    .replace(/_/g, " ")
    .replace(/\bLapse ind 1 PREDICTION\b/, "Lapse probability")
    .replace(/\bEXPLANATION 1 FEATURE NAME\b/, "Top feature");

  if (meta.type === "numeric") {
    const range = value as { min?: number; max?: number } | undefined;
    const decimals = (meta.max ?? 0) <= 1 ? 2 : 0;
    return (
      <div style={fieldStyle}>
        <label style={labelStyle}>{label}</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="number"
            placeholder={`Min (${meta.min?.toFixed(decimals)})`}
            value={range?.min ?? ""}
            onChange={(e) => {
              const min = e.target.value !== "" ? Number(e.target.value) : undefined;
              const max = range?.max;
              onChange(min !== undefined || max !== undefined ? { min, max } : null);
            }}
            style={inputStyle}
          />
          <input
            type="number"
            placeholder={`Max (${meta.max?.toFixed(decimals)})`}
            value={range?.max ?? ""}
            onChange={(e) => {
              const max = e.target.value !== "" ? Number(e.target.value) : undefined;
              const min = range?.min;
              onChange(min !== undefined || max !== undefined ? { min, max } : null);
            }}
            style={inputStyle}
          />
        </div>
      </div>
    );
  }

  if (meta.type === "categorical" && meta.values) {
    const selected = (value as string[] | undefined) ?? [];
    return (
      <div style={fieldStyle}>
        <label style={labelStyle}>{label}</label>
        <select
          multiple
          value={selected}
          onChange={(e) => {
            const vals = Array.from(e.target.selectedOptions).map((o) => o.value);
            onChange(vals.length > 0 ? vals : null);
          }}
          style={{ ...inputStyle, height: Math.min(meta.values.length * 22 + 4, 120) }}
        >
          {meta.values.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>
    );
  }

  return null;
}

const sectionLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.08em",
  color: "#888",
  textTransform: "uppercase",
  paddingTop: 4,
  borderTop: "1px solid #eee",
};
const fieldStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4 };
const labelStyle: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: "#555" };
const inputStyle: React.CSSProperties = {
  padding: "4px 8px",
  border: "1px solid #ddd",
  borderRadius: 4,
  fontSize: 13,
  flex: 1,
};
const btnStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "3px 10px",
  cursor: "pointer",
  background: "#f0f0f0",
  border: "1px solid #ccc",
  borderRadius: 4,
};
