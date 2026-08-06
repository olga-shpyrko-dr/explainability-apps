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

  // A regression target (arbitrary units, not a 0-1 probability) can't go
  // through the logit/sigmoid reconstruction below — sigmoid(13.26 days)
  // is meaningless. DataRobot's SHAP strengths are already additive directly
  // in the prediction's own units for both cases, so the fallback is simpler
  // than the classification path: use raw shap_strength as the bar height.
  const isProbability = prediction >= -1e-6 && prediction <= 1 + 1e-6;

  // Sort top features by absolute raw SHAP descending.
  const sorted = [...waterfall].sort(
    (a, b) => Math.abs(b.shap_strength) - Math.abs(a.shap_strength)
  );

  const sumShaps = sorted.reduce((s, w) => s + (w.shap_strength ?? 0), 0);

  let chartData: {
    label: string;
    shap_strength: number;
    shap_raw: number;
    actual_value: string | null;
    actual_value_short: string;
    feature_group: string;
    qualitative_strength: string | null;
  }[];
  let baseValue: number;

  if (isProbability) {
    // Reconstruct log-odds baseline = logit(prediction) − sum_of_shown_SHAPs.
    // This represents base_value + remaining + unexplained features.
    const logoddsBase = logit(prediction) - sumShaps;
    baseValue = sigmoid(logoddsBase);

    // Each bar = probability change when this feature's SHAP is added cumulatively.
    // sigmoid(cumLogodds after all N features) == prediction exactly.
    let cumLogodds = logoddsBase;
    chartData = sorted
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
  } else {
    // Regression: SHAP strengths are already additive in the target's own
    // units, so use them directly — no logit/sigmoid transform.
    baseValue = prediction - sumShaps;
    chartData = sorted.map((w) => ({
      label: w.feature_name,
      shap_strength: w.shap_strength ?? 0,
      shap_raw: w.shap_strength,
      actual_value: w.actual_value,
      actual_value_short: truncate(w.actual_value),
      feature_group: w.feature_group,
      qualitative_strength: w.qualitative_strength,
    }));
  }

  const isHigh = populationMean !== null ? prediction >= populationMean : prediction >= 0.5;
  const scoreLabel = isHigh ? highScoreLabel : lowScoreLabel;
  const scoreLabelColor = isHigh ? "#5C41FF" : "#6C6A6B";

  const fmtScore = (v: number) => (isProbability ? `${(v * 100).toFixed(1)}%` : v.toFixed(2));
  const fmtBar = (v: number) => (isProbability ? `${(v * 100).toFixed(1)}pp` : v.toFixed(3));

  return (
    <div>
      <h4 style={{ margin: "0 0 4px" }}>
        {rowId} —{" "}
        <span style={{ color: scoreLabelColor }}>{scoreLabel}</span>
        {" "}score: <b>{fmtScore(prediction)}</b>
      </h4>
      <p style={{ fontSize: 11, color: "#6C6A6B", margin: "0 0 12px", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
        Bars sum to <b>{fmtBar(prediction - baseValue)}</b> of the {fmtScore(prediction)} score.
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
            tickFormatter={(v) => fmtBar(v)}
            tick={{ fontSize: 11 }}
          />
          <YAxis type="category" dataKey="label" width={195} tick={{ fontSize: 11 }} />
          <ReferenceLine x={0} stroke="#aaa" />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload;
              const sign = d.shap_strength >= 0 ? "+" : "";
              const valStr = d.actual_value ? ` = ${d.actual_value}` : "";
              return (
                <div style={tooltipStyle}>
                  <div style={{ fontWeight: 500, marginBottom: 2 }}>{d.label}{valStr}</div>
                  <div style={{ color: d.shap_strength >= 0 ? "#5C41FF" : "#2a8a5a" }}>
                    {sign}{fmtBar(Math.abs(d.shap_strength))}
                  </div>
                </div>
              );
            }}
          />
          <Bar dataKey="shap_strength" radius={[0, 3, 3, 0]} label={<BarValueLabel data={chartData} isProbability={isProbability} />}>
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
  x, y, width, height, index, data, isProbability,
}: {
  x?: number; y?: number; width?: number; height?: number; index?: number;
  data: { actual_value_short: string; shap_strength: number }[];
  isProbability: boolean;
}) {
  if (x == null || y == null || width == null || height == null || index == null) return null;
  const entry = data[index];
  if (!entry?.actual_value_short || entry.shap_strength < 0) return null;

  const sign = entry.shap_strength >= 0 ? "+" : "";
  const label = isProbability
    ? `${sign}${(entry.shap_strength * 100).toFixed(1)}pp`
    : `${sign}${entry.shap_strength.toFixed(3)}`;
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
