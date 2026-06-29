import { useState, useEffect } from "react";
import type { LLMProviderInfo } from "../api";
import { fetchLLMProviders, postNarrative, postRowNarrative } from "../api";

interface Props {
  mode: "group" | "row";
  filters?: Record<string, unknown>;
  rowId?: string;
  nRows: number;
}

const PROVIDER_LABELS: Record<string, string> = {
  dr_gateway: "DR LLM Gateway",
  dr_deployment: "DR Deployed LLM",
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
};

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*"))
      return <em key={i}>{part.slice(1, -1)}</em>;
    return part;
  });
}

function NarrativeText({ text }: { text: string }) {
  const segments: React.ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) { i++; continue; }

    if (/^[-*•]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*•]\s/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*•]\s+/, ""));
        i++;
      }
      segments.push(
        <ul key={k++} style={{ margin: "4px 0 8px", paddingLeft: 20 }}>
          {items.map((item, j) => (
            <li key={j} style={{ lineHeight: 1.7, marginBottom: 2 }}>{renderInline(item)}</li>
          ))}
        </ul>
      );
    } else {
      const paraLines: string[] = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !/^[-*•]\s/.test(lines[i].trim())
      ) {
        paraLines.push(lines[i].trim());
        i++;
      }
      segments.push(
        <p key={k++} style={{ margin: "0 0 8px", lineHeight: 1.7 }}>
          {renderInline(paraLines.join(" "))}
        </p>
      );
    }
  }

  return <div>{segments}</div>;
}

export default function InlineNarrative({ mode, filters, rowId, nRows }: Props) {
  const [providers, setProviders] = useState<LLMProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [enabled, setEnabled] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [providerUsed, setProviderUsed] = useState("");
  const [disclaimer, setDisclaimer] = useState("");

  useEffect(() => {
    fetchLLMProviders()
      .then((data) => {
        setProviders(data.providers);
        setSelectedProvider(data.default);
      })
      .catch(() => {});
  }, []);

  // Reset when the source data changes
  useEffect(() => {
    setText("");
    setError("");
    setEnabled(false);
  }, [mode === "row" ? rowId : JSON.stringify(filters)]);

  async function generate() {
    if (nRows < 1) return;
    if (mode === "row" && !rowId) return;
    setLoading(true);
    setError("");
    try {
      const res =
        mode === "row"
          ? await postRowNarrative(rowId!, instruction, selectedProvider || undefined)
          : await postNarrative(filters ?? {}, instruction, false, selectedProvider || undefined);
      setText(res.narrative);
      setProviderUsed(res.provider_used);
      setDisclaimer(res.disclaimer);
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  function handleToggle(checked: boolean) {
    setEnabled(checked);
    if (checked && !text) generate();
  }

  const available = providers.filter((p) => p.available);
  const activeProvider = providers.find((p) => p.id === selectedProvider);
  const disabled = mode === "row" ? !rowId : nRows < 1;

  return (
    <div style={containerStyle}>
      {/* Header row: checkbox + label + compact provider select */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <label style={checkboxLabelStyle}>
          <input
            type="checkbox"
            checked={enabled}
            disabled={disabled}
            onChange={(e) => handleToggle(e.target.checked)}
            style={{ accentColor: "#5C41FF", width: 14, height: 14, cursor: disabled ? "not-allowed" : "pointer" }}
          />
          <span style={{ fontFamily: "'Fragment Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", color: disabled ? "#bbb" : "#6C6A6B" }}>
            AI summary
          </span>
        </label>

        {enabled && (
          <>
            <span style={viaStyle}>via</span>
            <select
              value={selectedProvider}
              onChange={(e) => { setSelectedProvider(e.target.value); setText(""); }}
              style={providerSelectStyle}
            >
              {available.map((p) => (
                <option key={p.id} value={p.id}>{PROVIDER_LABELS[p.id] ?? p.name}</option>
              ))}
            </select>
            {activeProvider?.model && (
              <span style={modelLabelStyle}>{activeProvider.model}</span>
            )}

            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Optional focus instruction…"
              style={instructionStyle}
              onKeyDown={(e) => e.key === "Enter" && generate()}
            />
            <button onClick={generate} disabled={loading} style={regenBtn}>
              {loading ? "…" : text ? "↺" : "Generate"}
            </button>
            {text && (
              <button onClick={() => navigator.clipboard.writeText(text)} style={copyBtn}>
                Copy
              </button>
            )}
          </>
        )}
      </div>

      {/* Narrative output */}
      {enabled && (
        <div style={{ marginTop: 12 }}>
          {error && (
            <p style={{ color: "#c0392b", fontSize: 12, margin: 0 }}>{error}</p>
          )}
          {loading && !text && (
            <p style={{ color: "#6C6A6B", fontSize: 13, margin: 0 }}>Generating…</p>
          )}
          {text && (
            <div style={narrativeBox}>
              {providerUsed && (
                <div style={narrativeEyebrow}>
                  Generated via {PROVIDER_LABELS[providerUsed] ?? providerUsed}
                </div>
              )}
              <NarrativeText text={text} />
              {disclaimer && (
                <p style={disclaimerStyle}>{disclaimer}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  marginTop: 20,
  paddingTop: 16,
  borderTop: "1px solid #E4E4E4",
};
const checkboxLabelStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  cursor: "pointer",
  userSelect: "none",
};
const viaStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#6C6A6B",
  fontFamily: "'DM Sans', system-ui, sans-serif",
};
const providerSelectStyle: React.CSSProperties = {
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 12,
  padding: "3px 6px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  background: "#F5F5F5",
  color: "#0B0B0B",
  cursor: "pointer",
};
const modelLabelStyle: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  color: "#6C6A6B",
  letterSpacing: "0.04em",
};
const instructionStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 140,
  padding: "3px 8px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  fontSize: 12,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  outline: "none",
  color: "#0B0B0B",
};
const regenBtn: React.CSSProperties = {
  padding: "3px 10px",
  background: "#5C41FF",
  color: "#FFFFFF",
  border: "none",
  borderRadius: 2,
  cursor: "pointer",
  fontSize: 12,
  fontFamily: "'DM Sans', system-ui, sans-serif",
};
const copyBtn: React.CSSProperties = {
  padding: "3px 8px",
  background: "#F5F5F5",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  cursor: "pointer",
  fontSize: 12,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  color: "#0B0B0B",
};
const narrativeBox: React.CSSProperties = {
  background: "#F5F5F5",
  border: "1px solid #E4E4E4",
  borderLeft: "3px solid #81FBA5",
  borderRadius: 2,
  padding: "12px 16px",
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  lineHeight: 1.7,
};
const narrativeEyebrow: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  textTransform: "uppercase" as const,
  letterSpacing: "0.06em",
  color: "#6C6A6B",
  marginBottom: 10,
};
const disclaimerStyle: React.CSSProperties = {
  fontFamily: "'Fragment Mono', monospace",
  fontSize: 9,
  textTransform: "uppercase" as const,
  letterSpacing: "0.05em",
  color: "#6C6A6B",
  marginTop: 10,
  borderTop: "1px solid #E4E4E4",
  paddingTop: 8,
  marginBottom: 0,
};
