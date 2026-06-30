import { useState, useEffect } from "react";
import type { AppConfig, ColumnMeta, ProfileAttribute } from "../api";
import { fetchColumns } from "../api";

interface Props {
  appConfig: AppConfig | null;
  filters: Record<string, unknown>;
  onChange: (filters: Record<string, unknown>) => void;
}

export default function CohortFilter({ appConfig, filters, onChange }: Props) {
  const [colMap, setColMap] = useState<Record<string, ColumnMeta>>({});

  useEffect(() => {
    fetchColumns().then((cols) => {
      const map: Record<string, ColumnMeta> = {};
      cols.forEach((c) => { map[c.name] = c; });
      setColMap(map);
    });
  }, []);

  function setFilter(col: string, value: unknown) {
    if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) {
      const next = { ...filters };
      delete next[col];
      onChange(next);
    } else {
      onChange({ ...filters, [col]: value });
    }
  }

  function clearAll() { onChange({}); }

  const activeCount = Object.keys(filters).length;

  if (!appConfig) {
    return <div style={{ color: "#888", fontSize: 13 }}>Loading filters…</div>;
  }

  const { profile_attributes, score_filter, top_explanation_filter, prediction_col } = appConfig;

  // The top explanation column name derived from config
  const topFeatureCol = `EXPLANATION_${top_explanation_filter.explanation_slot}_FEATURE_NAME`;
  const scoreCol = prediction_col;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontFamily: "'Fragment Mono', monospace", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "#5C41FF", fontWeight: 400 }}>Filters</h3>
        {activeCount > 0 && (
          <button onClick={clearAll} style={btnStyle}>
            Clear all ({activeCount})
          </button>
        )}
      </div>

      {/* Profile attributes from config */}
      {profile_attributes.length > 0 && (
        <>
          <div style={sectionLabel}>ATTRIBUTES</div>
          {profile_attributes.map((attr) => {
            const meta = colMap[attr.column];
            if (!meta) return null;
            return (
              <FilterControl
                key={attr.column}
                meta={meta}
                displayName={attr.display_name}
                filterType={attr.filter_type}
                value={filters[attr.column]}
                onChange={(v) => setFilter(attr.column, v)}
              />
            );
          })}
        </>
      )}

      {/* Score filter */}
      {score_filter.show && colMap[scoreCol] && (
        <>
          <div style={sectionLabel}>SCORE</div>
          <FilterControl
            meta={colMap[scoreCol]}
            displayName={score_filter.display_name}
            filterType="range"
            value={filters[scoreCol]}
            onChange={(v) => setFilter(scoreCol, v)}
          />
        </>
      )}

      {/* Top explanation feature filter */}
      {top_explanation_filter.show && colMap[topFeatureCol]?.values && (
        <>
          <div style={sectionLabel}>TOP DRIVER</div>
          <MultiCheckFilter
            label={top_explanation_filter.display_name}
            values={colMap[topFeatureCol].values!}
            selected={(filters[topFeatureCol] as string[] | undefined) ?? []}
            onChange={(v) => setFilter(topFeatureCol, v.length > 0 ? v : null)}
          />
        </>
      )}

    </div>
  );
}

// ---------------------------------------------------------------------------
// FilterControl — renders the right widget based on filter_type or column meta
// ---------------------------------------------------------------------------

function FilterControl({
  meta,
  displayName,
  filterType,
  value,
  onChange,
}: {
  meta: ColumnMeta;
  displayName: string;
  filterType: ProfileAttribute["filter_type"];
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  // Toggle: two-option categorical (yes/no or similar)
  if (filterType === "toggle" && meta.type === "categorical" && meta.values) {
    const vals = meta.values;
    const selected = (value as string[] | undefined) ?? [];
    return (
      <div style={fieldStyle}>
        <label style={labelStyle}>{displayName}</label>
        <div style={{ display: "flex", gap: 6 }}>
          {vals.map((v) => (
            <button
              key={v}
              onClick={() => {
                const next = selected.includes(v)
                  ? selected.filter((x) => x !== v)
                  : [...selected, v];
                onChange(next.length > 0 ? next : null);
              }}
              style={{
                ...toggleBtn,
                ...(selected.includes(v) ? toggleBtnActive : {}),
              }}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // Range: numeric
  if (filterType === "range" || meta.type === "numeric") {
    const range = value as { min?: number; max?: number } | undefined;
    const decimals = (meta.max ?? 0) <= 1 ? 2 : 0;
    return (
      <div style={fieldStyle}>
        <label style={labelStyle}>{displayName}</label>
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

  // Multiselect: categorical
  if (meta.type === "categorical" && meta.values) {
    const selected = (value as string[] | undefined) ?? [];
    return (
      <div style={fieldStyle}>
        <label style={labelStyle}>{displayName}</label>
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

// ---------------------------------------------------------------------------
// MultiCheckFilter — scrollable checkbox list for the top explanation filter
// ---------------------------------------------------------------------------

function MultiCheckFilter({
  label,
  values,
  selected,
  onChange,
}: {
  label: string;
  values: string[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  return (
    <div style={fieldStyle}>
      <label style={labelStyle}>{label}</label>
      <div style={{ maxHeight: 140, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
        {values.map((v) => (
          <label
            key={v}
            style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}
          >
            <input
              type="checkbox"
              checked={selected.includes(v)}
              onChange={() => {
                const next = selected.includes(v)
                  ? selected.filter((x) => x !== v)
                  : [...selected, v];
                onChange(next);
              }}
            />
            {v}
          </label>
        ))}
      </div>
    </div>
  );
}

const sectionLabel: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  letterSpacing: "0.08em",
  color: "#5C41FF",
  textTransform: "uppercase",
  paddingTop: 10,
  borderTop: "1px solid #E4E4E4",
};
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
  flex: 1,
  outline: "none",
};
const btnStyle: React.CSSProperties = {
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 11,
  padding: "3px 10px",
  cursor: "pointer",
  background: "#F5F5F5",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  color: "#0B0B0B",
};
const toggleBtn: React.CSSProperties = {
  padding: "4px 12px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  cursor: "pointer",
  background: "#FFFFFF",
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 12,
  color: "#6C6A6B",
};
const toggleBtnActive: React.CSSProperties = {
  background: "#0B0B0B",
  color: "#81FBA5",
  borderColor: "#0B0B0B",
};
