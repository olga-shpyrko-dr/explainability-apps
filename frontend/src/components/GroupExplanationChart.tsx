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
}

const GROUP_COLORS: Record<string, string> = {
  "Policy & Product": "#5C41FF",
  "Policy Portfolio": "#909BF5",
  "Agent / Adviser": "#44BFFC",
  Sociodemographic: "#81FBA5",
  "Financial Profile": "#61DFCF",
  "Engagement & Reviews": "#BFFD7E",
  Persona: "#E4E4E4",
  Other: "#ccc",
};

type Direction = "all" | "positive" | "negative";

export default function GroupExplanationChart({ groups, loading }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [direction, setDirection] = useState<Direction>("all");

  if (loading) return <div style={placeholderStyle}>Loading group explanations…</div>;
  if (!groups.length) return <div style={placeholderStyle}>No explanation data for this cohort.</div>;

  const visibleGroups = groups.filter((g) => {
    if (direction === "positive") return g.avg_shap > 0;
    if (direction === "negative") return g.avg_shap < 0;
    return true;
  });

  const chartData = visibleGroups.map((g) => ({ ...g, abs_shap: Math.abs(g.avg_shap) }));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <p style={{ fontSize: 12, color: "#888", margin: 0 }}>
          Based on top-4 explanations only — groups with diffuse signal may be underweighted.
        </p>
        <div style={{ display: "flex", gap: 6, flexShrink: 0, marginLeft: 16 }}>
          {(["all", "positive", "negative"] as Direction[]).map((d) => (
            <button
              key={d}
              onClick={() => setDirection(d)}
              style={{
                fontSize: 11,
                padding: "3px 10px",
                cursor: "pointer",
                border: "1px solid",
                borderRadius: 10,
                borderColor: direction === d ? (d === "positive" ? "#e05252" : d === "negative" ? "#3db87a" : "#555") : "#ccc",
                background: direction === d ? (d === "positive" ? "#fce8e8" : d === "negative" ? "#e8fdf0" : "#eee") : "#fff",
                color: direction === d ? (d === "positive" ? "#8b2020" : d === "negative" ? "#1a6b3a" : "#333") : "#888",
              }}
            >
              {d === "all" ? "All" : d === "positive" ? "▲ Increases risk" : "▼ Reduces risk"}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={Math.max(chartData.length * 44 + 40, 60)}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 40, left: 160, bottom: 4 }}
          key={direction}
        >
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis
            type="category"
            dataKey="feature_group"
            tick={{ fontSize: 12 }}
            width={155}
          />
          <ReferenceLine x={0} stroke="#999" />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload as GroupStat;
              return (
                <div style={tooltipStyle}>
                  <b>{d.feature_group}</b>
                  <div>Avg SHAP: {d.avg_shap.toFixed(5)}</div>
                  <div>Coverage: {d.n_rows_with_coverage} rows ({d.coverage_pct}%)</div>
                  <div style={{ fontSize: 11, color: "#888", marginTop: 4 }}>
                    Click to {expanded === d.feature_group ? "collapse" : "expand"} features
                  </div>
                </div>
              );
            }}
          />
          <Bar
            dataKey="avg_shap"
            radius={[0, 3, 3, 0]}
            cursor="pointer"
            onClick={(data: GroupStat) => {
              setExpanded(expanded === data.feature_group ? null : data.feature_group);
            }}
          >
            {chartData.map((entry) => (
              <Cell
                key={entry.feature_group}
                fill={entry.avg_shap >= 0 ? "#e05252" : "#81FBA5"}
                opacity={expanded && expanded !== entry.feature_group ? 0.4 : 1}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {expanded && (
        <FeatureDrillDown
          group={groups.find((g) => g.feature_group === expanded)!}
          onClose={() => setExpanded(null)}
        />
      )}
    </div>
  );
}

function FeatureDrillDown({
  group,
  onClose,
}: {
  group: GroupStat;
  onClose: () => void;
}) {
  const features = group.top_features ?? [];
  const color = GROUP_COLORS[group.feature_group] ?? "#ccc";

  return (
    <div style={drillStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h4 style={{ margin: 0, color: "#222" }}>{group.feature_group} — top features</h4>
        <button onClick={onClose} style={{ cursor: "pointer", background: "none", border: "none", fontSize: 16 }}>
          ✕
        </button>
      </div>
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 8px" }}>
        {group.n_rows_with_coverage} of cohort rows had ≥1 feature from this group in top-4 explanations ({group.coverage_pct}% coverage)
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
            <Tooltip
              formatter={(val: unknown) => [(val as number).toFixed(5), "Avg SHAP"]}
            />
            <Bar dataKey="avg_shap" radius={[0, 3, 3, 0]}>
              {features.map((f) => (
                <Cell
                  key={f.feature_name}
                  fill={f.avg_shap >= 0 ? "#e05252" : "#81FBA5"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

const placeholderStyle: React.CSSProperties = { padding: 24, color: "#888" };
const tooltipStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #ddd",
  borderRadius: 6,
  padding: "8px 12px",
  fontSize: 13,
};
const drillStyle: React.CSSProperties = {
  marginTop: 16,
  padding: 16,
  background: "#f9f9f9",
  borderRadius: 8,
  border: "1px solid #e0e0e0",
};
