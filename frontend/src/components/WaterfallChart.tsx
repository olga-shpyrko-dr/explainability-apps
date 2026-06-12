import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  Cell,
  LabelList,
  ResponsiveContainer,
} from "recharts";
import type { WaterfallEntry } from "../api";

interface Props {
  rowId: string;
  prediction: number;
  waterfall: WaterfallEntry[];
  loading: boolean;
}


export default function WaterfallChart({ rowId, prediction, waterfall, loading }: Props) {
  if (loading) return <div style={{ color: "#888" }}>Loading…</div>;
  if (!waterfall.length) return <div style={{ color: "#888" }}>No explanation for this policy.</div>;

  // Sort by absolute SHAP strength descending
  const chartData = [...waterfall]
    .sort((a, b) => Math.abs(b.shap_strength) - Math.abs(a.shap_strength))
    .map((w) => ({
      label: w.feature_name,
      shap_strength: w.shap_strength,
      actual_value: w.actual_value,
      feature_group: w.feature_group,
      qualitative_strength: w.qualitative_strength,
    }));

  return (
    <div>
      <h4 style={{ margin: "0 0 4px" }}>
        Policy {rowId} — Lapse propensity: <b>{(prediction * 100).toFixed(1)}%</b>
      </h4>
      <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
        Top-4 SHAP contributions. Each bar shows the independent influence of that feature —
        positive (red) increases lapse risk, negative (green) reduces it.
        Values are not a decomposition of the prediction score.
      </p>
      <ResponsiveContainer width="100%" height={chartData.length * 52 + 50}>
        <BarChart
          layout="vertical"
          data={chartData}
          margin={{ top: 4, right: 60, left: 200, bottom: 4 }}
        >
          <XAxis type="number" domain={["auto", "auto"]} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={195} tick={{ fontSize: 11 }} />
          <ReferenceLine x={0} stroke="#aaa" />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload;
              const sign = d.shap_strength > 0 ? "+" : "";
              return (
                <div style={tooltipStyle}>
                  <b>{d.label}</b>
                  <div>Value: {d.actual_value}</div>
                  <div>
                    SHAP: {sign}{d.shap_strength.toFixed(5)}{" "}
                    <span style={{ color: "#888" }}>({d.qualitative_strength})</span>
                  </div>
                  <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
                    Group: {d.feature_group}
                  </div>
                </div>
              );
            }}
          />
          <Bar dataKey="shap_strength" radius={[0, 3, 3, 0]}>
            {chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={entry.shap_strength >= 0 ? "#e05252" : "#81FBA5"}
              />
            ))}
            <LabelList
              dataKey="actual_value"
              position="right"
              style={{ fontSize: 11, fill: "#555" }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

    </div>
  );
}

const tooltipStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #ddd",
  borderRadius: 6,
  padding: "8px 12px",
  fontSize: 13,
};
