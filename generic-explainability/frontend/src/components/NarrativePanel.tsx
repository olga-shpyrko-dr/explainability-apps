import { useState, useEffect } from "react";
import type { LLMProviderInfo } from "../api";
import { fetchLLMProviders, postNarrative } from "../api";

interface Props {
  filters: Record<string, unknown>;
  nRows: number;
  cohortWarningMinRows: number;
}

const PROVIDER_LABELS: Record<string, string> = {
  dr_gateway: "DR LLM Gateway",
  dr_deployment: "DR Deployed LLM",
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
};

export default function NarrativePanel({ filters, nRows, cohortWarningMinRows }: Props) {
  const [providers, setProviders] = useState<LLMProviderInfo[]>([]);
  const [defaultProvider, setDefaultProvider] = useState<string>("");
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [text, setText] = useState("");
  const [providerUsed, setProviderUsed] = useState("");
  const [disclaimer, setDisclaimer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [instruction, setInstruction] = useState("");

  useEffect(() => {
    fetchLLMProviders()
      .then((data) => {
        setProviders(data.providers);
        setDefaultProvider(data.default);
        setSelectedProvider(data.default);
      })
      .catch(() => {});
  }, []);

  async function generate() {
    if (nRows < 1) return;
    setLoading(true);
    setError("");
    try {
      const res = await postNarrative(filters, instruction, false, selectedProvider || undefined);
      setText(res.narrative);
      setProviderUsed(res.provider_used);
      setDisclaimer(res.disclaimer);
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  function copyText() {
    navigator.clipboard.writeText(text);
  }

  const available = providers.filter((p) => p.available);
  const unavailable = providers.filter((p) => !p.available);

  return (
    <div>
      {providers.length > 0 && (
        <div style={providerRowStyle}>
          <span style={{ fontFamily: "'Fragment Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", color: "#6C6A6B", whiteSpace: "nowrap" }}>
            LLM Provider
          </span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {available.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedProvider(p.id)}
                title={`${p.notes}${p.model ? `\nModel: ${p.model}` : ""}`}
                style={{ ...providerBtn, ...(selectedProvider === p.id ? providerBtnActive : {}) }}
              >
                {PROVIDER_LABELS[p.id] ?? p.name}
                {p.id === defaultProvider && selectedProvider !== p.id && (
                  <span style={{ fontSize: 10, color: "#888", marginLeft: 4 }}>(default)</span>
                )}
              </button>
            ))}
            {unavailable.map((p) => (
              <button
                key={p.id}
                disabled
                title={`Not configured — set credentials in .env\n${p.notes}`}
                style={{ ...providerBtn, ...providerBtnDisabled }}
              >
                {PROVIDER_LABELS[p.id] ?? p.name}
              </button>
            ))}
          </div>
          {selectedProvider && (
            <span style={{ fontSize: 11, color: "#666", marginLeft: 8 }}>
              {providers.find((p) => p.id === selectedProvider)?.model
                ? `model: ${providers.find((p) => p.id === selectedProvider)?.model}`
                : ""}
            </span>
          )}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Optional: focus instruction (e.g. 'Focus on financial stress indicators')"
          style={instructionInput}
        />
        <button onClick={generate} disabled={loading || nRows < 1} style={primaryBtn}>
          {loading ? "Generating…" : "Generate narrative"}
        </button>
        {text && (
          <button onClick={copyText} style={secondaryBtn}>
            Copy
          </button>
        )}
      </div>

      {nRows > 0 && nRows < cohortWarningMinRows && (
        <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: 12, color: "#0B0B0B", background: "#FFFF54", padding: "6px 10px", borderRadius: 2, margin: "0 0 8px", display: "inline-block" }}>
          Cohort has only {nRows} rows — group-level averages may not be stable.
        </p>
      )}

      {error && <p style={{ color: "#c0392b", fontSize: 13, fontFamily: "'DM Sans', system-ui, sans-serif" }}>Error: {error}</p>}

      {text && (
        <div style={narrativeBox}>
          {providerUsed && (
            <div style={{ fontFamily: "'Fragment Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", color: "#6C6A6B", marginBottom: 12 }}>
              Generated via {PROVIDER_LABELS[providerUsed] ?? providerUsed}
            </div>
          )}
          <div style={{ whiteSpace: "pre-wrap" }}>{text}</div>
          {disclaimer && (
            <p style={{ fontFamily: "'Fragment Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6C6A6B", marginTop: 12, borderTop: "1px solid #E4E4E4", paddingTop: 8 }}>
              {disclaimer}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

const providerRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  marginBottom: 14,
  marginTop: 12,
  padding: "10px 14px",
  background: "#F5F5F5",
  borderRadius: 2,
  border: "1px solid #E4E4E4",
  flexWrap: "wrap",
};
const providerBtn: React.CSSProperties = {
  padding: "4px 12px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  cursor: "pointer",
  background: "#FFFFFF",
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: 12,
  color: "#0B0B0B",
};
const providerBtnActive: React.CSSProperties = {
  background: "#0B0B0B",
  color: "#81FBA5",
  borderColor: "#0B0B0B",
  fontWeight: 500,
};
const providerBtnDisabled: React.CSSProperties = { opacity: 0.35, cursor: "not-allowed", color: "#6C6A6B" };
const instructionInput: React.CSSProperties = {
  flex: 1,
  padding: "7px 10px",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  minWidth: 200,
  outline: "none",
};
const primaryBtn: React.CSSProperties = {
  padding: "7px 18px",
  background: "#5C41FF",
  color: "#FFFFFF",
  border: "none",
  borderRadius: 2,
  cursor: "pointer",
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontWeight: 500,
};
const secondaryBtn: React.CSSProperties = {
  padding: "7px 12px",
  background: "#F5F5F5",
  border: "1px solid #E4E4E4",
  borderRadius: 2,
  cursor: "pointer",
  fontSize: 13,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  color: "#0B0B0B",
};
const narrativeBox: React.CSSProperties = {
  background: "#F5F5F5",
  border: "1px solid #E4E4E4",
  borderLeft: "3px solid #81FBA5",
  borderRadius: 2,
  padding: 16,
  fontSize: 14,
  fontFamily: "'DM Sans', system-ui, sans-serif",
  lineHeight: 1.7,
};
