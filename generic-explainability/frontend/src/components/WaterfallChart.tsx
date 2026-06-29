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
import type { WaterfallEntry } from "../api";

interface Props {
  rowId: string;
  prediction: number;
  waterfall: WaterfallEntry[];
  loading: boolean;
  highScoreLabel: string;
  lowScoreLabel: string;
  populationMean: number | null;
  factorPositiveLabel: string;
  factorNegativeLabel: string;
}

export default function WaterfallChart({
  rowId,
  prediction,
  waterfall,
  loading,
  highScoreLabel,
  lowScoreLabel,
  populationMean,
  factorPositiveLabel,
  factorNegativeLabel,
}: Props) {
  if (loading) return <div style={{ color: "#888" }}>Loading…</div>;
  if (!waterfall.length) return <div style={{ color: "#888" }}>No explanation for this row.</div>;

  const truncate = (s: string | null, max = 30) =>
    s && s.length > max ? s.slice(0, max) + "…" : (s ?? "");

  const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
  const logit = (p: number) => {
    const c = Math.max(1e-7, Math.min(1 - 1e-7, p));
    return Math.log(c / (1 - c));
  };

  // Sort top features by absolute raw SHAP descending.
  const sorted = [...waterfall].sort(
    (a, b) => Math.abs(b.shap_strength) - Math.abs(a.shap_strength)
  );

  // Reconstruct log-odds baseline = logit(prediction) − sum_of_shown_SHAPs.
  // This represents base_value + remaining + unexplained features.
  const sumShaps = sorted.reduce((s, w) => s + (w.shap_strength ?? 0), 0);
  const logoddsBase = logit(prediction) - sumShaps;
  const baseProb = sigmoid(logoddsBase);

  // Each bar = probability change when this feature's SHAP is added cumulatively.
  // sigmoid(cumLogodds after all N features) == prediction exactly.
  let cumLogodds = logoddsBase;
  const chartData = sorted
    .map((w) => {
      const probBefore = sigmoid(cumLogodds);
      cumLogodds += w.shap_strength ?? 0;
      const probAfter = sigmoid(cumLogodds);
      return {
        label: w.feature_name,
        shap_strength: probAfter - probBefore,
        shap_raw: w.shap_strength,
        actual_value: w.actual_value,
        actual_value_short: truncate(w.actual_value),
        feature_group: w.feature_group,
        qualitative_strength: w.qualitative_strength,
      };
    })
    .sort((a, b) => Math.abs(b.shap_strength) - Math.abs(a.shap_strength));

  const isHigh = populationMean !== null ? prediction >= populationMean : prediction >= 0.5;
  const scoreLabel = isHigh ? highScoreLabel : lowScoreLabel;
  const scoreLabelColor = isHigh ? "#5C41FF" : "#6C6A6B";

  return (
    <div>
      <h4 style={{ margin: "0 0 4px" }}>
        {rowId} —{" "}
        <span style={{ color: scoreLabelColor }}>{scoreLabel}</span>
        {" "}score: <b>{(prediction * 100).toFixed(1)}%</b>
      </h4>
      <p style={{ fontSize: 11, color: "#6C6A6B", margin: "0 0 12px", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
        Bars sum to <b>{((prediction - baseProb) * 100).toFixed(1)} pp</b> of the {(prediction * 100).toFixed(1)}% score.
        Purple = {factorPositiveLabel}. Green = {factorNegativeLabel}.
      </p>
      <ResponsiveContainer width="100%" height={chartData.length * 52 + 50}>
        <BarChart
          layout="vertical"
          data={chartData}
          margin={{ top: 4, right: 200, left: 200, bottom: 4 }}
        >
          <XAxis
            type="number"
            domain={["auto", "auto"]}
            tickFormatter={(v) => `${(v * 100).toFixed(1)}pp`}
            tick={{ fontSize: 11 }}
          />
          <YAxis type="category" dataKey="label" width={195} tick={{ fontSize: 11 }} />
          <ReferenceLine x={0} stroke="#aaa" />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload;
              const sign = d.shap_strength >= 0 ? "+" : "";
              const pp = (d.shap_strength * 100).toFixed(2);
              const valStr = d.actual_value ? ` = ${d.actual_value}` : "";
              return (
                <div style={tooltipStyle}>
                  <div style={{ fontWeight: 500, marginBottom: 2 }}>{d.label}{valStr}</div>
                  <div style={{ color: d.shap_strength >= 0 ? "#5C41FF" : "#2a8a5a" }}>
                    {sign}{pp} pp
                  </div>
                </div>
              );
            }}
          />
          <Bar dataKey="shap_strength" radius={[0, 3, 3, 0]} label={<BarValueLabel data={chartData} />}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.shap_strength >= 0 ? "#909BF5" : "#81FBA5"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Custom bar label — only shown for positive bars (to the right of bar end).
// Negative bars rely on the tooltip to avoid overlapping the Y-axis labels.
function BarValueLabel({
  x, y, width, height, index, data,
}: {
  x?: number; y?: number; width?: number; height?: number; index?: number;
  data: { actual_value_short: string; shap_strength: number }[];
}) {
  if (x == null || y == null || width == null || height == null || index == null) return null;
  const entry = data[index];
  if (!entry?.actual_value_short || entry.shap_strength < 0) return null;

  const sign = entry.shap_strength >= 0 ? "+" : "";
  const label = `${sign}${(entry.shap_strength * 100).toFixed(1)}pp`;
  return (
    <text x={x + width + 6} y={y + height / 2} fontSize={11} fill="#555" dominantBaseline="middle" textAnchor="start">
      {label}
    </text>
  );
}

const tooltipStyle: React.CSSProperties = {
  background: "#FFFFFF",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  padding: "8px 12px",
  fontSize: 12,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  maxWidth: 280,
  lineHeight: 1.5,
};
