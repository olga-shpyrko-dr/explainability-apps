import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  Cell,
  ResponsiveContainer,
} from "recharts";
import type { GroupStat } from "../api";

interface Props {
  groups: GroupStat[];
  loading: boolean;
  factorPositiveLabel: string;
  factorNegativeLabel: string;
  maxExplanations: number;
}

// Auto-assign colours from a palette — no hardcoded group names
const PALETTE = [
  "#5C41FF", "#909BF5", "#44BFFC", "#81FBA5",
  "#61DFCF", "#BFFD7E", "#FFFF54", "#E4E4E4",
];

function groupColor(index: number, isOther: boolean): string {
  if (isOther) return "#ccc";
  return PALETTE[index % PALETTE.length];
}

type Direction = "all" | "positive" | "negative";

export default function GroupExplanationChart({
  groups,
  loading,
  factorPositiveLabel,
  factorNegativeLabel,
  maxExplanations,
}: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [direction, setDirection] = useState<Direction>("all");

  if (loading) return <div style={placeholderStyle}>Loading group explanations…</div>;
  if (!groups.length) return <div style={placeholderStyle}>No explanation data for this cohort.</div>;

  const visibleGroups = groups.filter((g) => {
    if (direction === "positive") return g.sum_shap > 0;
    if (direction === "negative") return g.sum_shap < 0;
    return true;
  });

  // Build a stable colour index from the full groups list (not visible-only)
  const groupIndex = Object.fromEntries(
    groups.map((g, i) => [g.feature_group, i])
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <p style={{ fontSize: 11, color: "#6C6A6B", margin: 0, fontFamily: "'DM Sans', system-ui, sans-serif" }}>
          Based on top-{maxExplanations} explanations only — groups with diffuse signal may be underweighted.
        </p>
        <div style={{ display: "flex", gap: 6, flexShrink: 0, marginLeft: 16 }}>
          {(["all", "positive", "negative"] as Direction[]).map((d) => (
            <button
              key={d}
              onClick={() => setDirection(d)}
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: 11,
                padding: "3px 10px",
                cursor: "pointer",
                border: "1px solid",
                borderRadius: 2,
                borderColor: direction === d ? "#0B0B0B" : "#E4E4E4",
                background:
                  direction === d
                    ? d === "positive" ? "#909BF5" : d === "negative" ? "#81FBA5" : "#0B0B0B"
                    : "#FFFFFF",
                color:
                  direction === d
                    ? d === "positive" ? "#0B0B0B" : d === "negative" ? "#0B0B0B" : "#81FBA5"
                    : "#6C6A6B",
              }}
            >
              {d === "all" ? "All" : d === "positive" ? "▲ Increases" : "▼ Reduces"}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={Math.max(visibleGroups.length * 44 + 40, 60)}>
        <BarChart
          data={visibleGroups}
          layout="vertical"
          margin={{ top: 4, right: 40, left: 160, bottom: 4 }}
          key={direction}
        >
          <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(4)} />
          <YAxis type="category" dataKey="feature_group" tick={{ fontSize: 12 }} width={155} />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload as GroupStat;
              const dir = d.sum_shap >= 0 ? factorPositiveLabel : factorNegativeLabel;
              return (
                <div style={tooltipStyle}>
                  <b>{d.feature_group}</b>
                  <div>Avg |SHAP|: {d.avg_abs_shap.toFixed(5)}</div>
                  <div>Net direction: {dir}</div>
                  <div>Coverage: {d.n_rows_with_coverage} rows ({d.coverage_pct}%)</div>
                  <div style={{ fontSize: 11, color: "#888", marginTop: 4 }}>
                    Click to {expanded === d.feature_group ? "collapse" : "expand"} features
                  </div>
                </div>
              );
            }}
          />
          <Bar
            dataKey="avg_abs_shap"
            radius={[0, 3, 3, 0]}
            cursor="pointer"
            onClick={(data: GroupStat) => {
              setExpanded(expanded === data.feature_group ? null : data.feature_group);
            }}
          >
            {visibleGroups.map((entry) => (
              <Cell
                key={entry.feature_group}
                fill={entry.sum_shap >= 0 ? "#909BF5" : "#81FBA5"}
                opacity={expanded && expanded !== entry.feature_group ? 0.4 : 1}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {expanded && (
        <FeatureDrillDown
          group={groups.find((g) => g.feature_group === expanded)!}
          color={groupColor(groupIndex[expanded] ?? 0, expanded === "Other")}
          onClose={() => setExpanded(null)}
          maxExplanations={maxExplanations}
        />
      )}
    </div>
  );
}

function FeatureDrillDown({
  group,
  color,
  onClose,
  maxExplanations,
}: {
  group: GroupStat;
  color: string;
  onClose: () => void;
  maxExplanations: number;
}) {
  const features = group.top_features ?? [];

  return (
    <div style={drillStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h4 style={{ margin: 0, color: "#222" }}>
          <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 2, background: color, marginRight: 8 }} />
          {group.feature_group} — top features
        </h4>
        <button onClick={onClose} style={{ cursor: "pointer", background: "none", border: "none", fontSize: 16 }}>
          ✕
        </button>
      </div>
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 8px" }}>
        {group.n_rows_with_coverage} of cohort rows had ≥1 feature from this group in top-{maxExplanations} explanations ({group.coverage_pct}% coverage)
      </p>
      {features.length === 0 ? (
        <p style={{ fontSize: 12 }}>No feature detail available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={features.length * 40 + 30}>
          <BarChart
            data={features}
            layout="vertical"
            margin={{ top: 4, right: 40, left: 200, bottom: 4 }}
          >
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="feature_name" tick={{ fontSize: 11 }} width={195} />
            <ReferenceLine x={0} stroke="#bbb" />
            <Tooltip formatter={(val: unknown) => [(val as number).toFixed(5), "Avg SHAP"]} />
            <Bar dataKey="avg_shap" radius={[0, 3, 3, 0]}>
              {features.map((f) => (
                <Cell key={f.feature_name} fill={f.avg_shap >= 0 ? "#909BF5" : "#81FBA5"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

const placeholderStyle: React.CSSProperties = { padding: 24, color: "#6C6A6B", fontFamily: "'DM Sans', system-ui, sans-serif" };
const tooltipStyle: React.CSSProperties = {
  background: "#FFFFFF",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  padding: "8px 12px",
  fontSize: 12,
  fontFamily: "'DM Sans', system-ui, sans-serif",
};
const drillStyle: React.CSSProperties = {
  marginTop: 16,
  padding: 16,
  background: "#F5F5F5",
  borderRadius: 2,
  border: "1px solid #E4E4E4",
};
