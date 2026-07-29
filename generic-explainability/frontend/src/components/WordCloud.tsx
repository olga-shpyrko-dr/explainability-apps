import type { WordFrequency } from "../api";

const MIN_FONT_PX = 13;
const MAX_FONT_PX = 30;

function fontSizeFor(count: number, min: number, max: number): number {
  if (max === min) return (MIN_FONT_PX + MAX_FONT_PX) / 2;
  const t = (count - min) / (max - min);
  return MIN_FONT_PX + t * (MAX_FONT_PX - MIN_FONT_PX);
}

interface Props {
  words: WordFrequency[];
}

// Magnitude is encoded by size, not hue (dataviz: sequential = one hue) — every word
// renders in the same brand color, so identity never depends on distinguishing colors.
export default function WordCloud({ words }: Props) {
  if (!words.length) {
    return <p style={emptyStyle}>No words match the current filters.</p>;
  }

  const counts = words.map((w) => w.count);
  const min = Math.min(...counts);
  const max = Math.max(...counts);

  return (
    <div role="list" aria-label="Word frequency cloud" style={cloudStyle}>
      {words.map(({ word, count }) => (
        <span
          key={word}
          role="listitem"
          tabIndex={0}
          title={`${word}: ${count}`}
          style={{ ...wordStyle, fontSize: fontSizeFor(count, min, max) }}
        >
          {word}
        </span>
      ))}
    </div>
  );
}

const cloudStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "baseline",
  gap: "6px 14px",
  padding: 8,
};

const wordStyle: React.CSSProperties = {
  color: "#5C41FF",
  lineHeight: 1,
  fontWeight: 500,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  cursor: "default",
};

const emptyStyle: React.CSSProperties = {
  fontSize: 13,
  color: "#6C6A6B",
  fontFamily: "'DM Sans', system-ui, sans-serif",
  margin: 0,
};
