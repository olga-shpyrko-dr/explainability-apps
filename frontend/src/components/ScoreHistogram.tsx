import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface HistBin {
  bin_start: number;
  bin_end: number;
  count: number;
}

interface Props {
  data: HistBin[];
  height?: number;
}

export default function ScoreHistogram({ data, height = 160 }: Props) {
  if (!data.length) return null;
  const chartData = data.map((b) => ({
    label: `${(b.bin_start * 100).toFixed(0)}–${(b.bin_end * 100).toFixed(0)}`,
    count: b.count,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={3} />
        <YAxis tick={{ fontSize: 10 }} />
        <Tooltip formatter={(v: unknown) => [v as number, "Policies"]} />
        <Bar dataKey="count" fill="#5C41FF" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
