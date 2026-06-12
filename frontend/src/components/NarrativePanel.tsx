import { useState, useEffect } from "react";
import type { LLMProviderInfo } from "../api";
import { fetchLLMProviders, postNarrative } from "../api";

interface Props {
  filters: Record<string, unknown>;
  nRows: number;
}

const PROVIDER_LABELS: Record<string, string> = {
  dr_gateway: "DR LLM Gateway",
  dr_deployment: "DR Deployed LLM",
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
};

export default function NarrativePanel({ filters, nRows }: Props) {
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
    fetchLLMProviders().then((data) => {
      setProviders(data.providers);
      setDefaultProvider(data.default);
      setSelectedProvider(data.default);
    }).catch(() => {
      // backend not yet ready — silent fail
    });
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
      {/* Provider selector */}
      {providers.length > 0 && (
        <div style={providerRowStyle}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#555", whiteSpace: "nowrap" }}>
            LLM provider
          </span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {available.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedProvider(p.id)}
                title={`${p.notes}${p.model ? `\nModel: ${p.model}` : ""}`}
                style={{
                  ...providerBtn,
                  ...(selectedProvider === p.id ? providerBtnActive : {}),
                }}
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
            <ProviderDetail provider={providers.find((p) => p.id === selectedProvider)} />
          )}
        </div>
      )}

      {/* Controls row */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Optional: focus instruction (e.g. 'Write for a financial adviser')"
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

      {nRows < 30 && nRows > 0 && (
        <p style={{ fontSize: 12, color: "#e08000", margin: "0 0 8px" }}>
          ⚠ Cohort has only {nRows} rows — group-level averages may not be stable.
        </p>
      )}

      {error && <p style={{ color: "red", fontSize: 13 }}>Error: {error}</p>}

      {text && (
        <div style={narrativeBox}>
          {providerUsed && (
            <div style={{ fontSize: 11, color: "#888", marginBottom: 8 }}>
              Generated via {PROVIDER_LABELS[providerUsed] ?? providerUsed}
            </div>
          )}
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{text}</div>
          {disclaimer && (
            <p style={{ fontSize: 11, color: "#999", marginTop: 12, borderTop: "1px solid #eee", paddingTop: 8 }}>
              {disclaimer}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ProviderDetail({ provider }: { provider?: LLMProviderInfo }) {
  if (!provider) return null;
  return (
    <span style={{ fontSize: 11, color: "#666", marginLeft: 8 }}>
      {provider.model ? `model: ${provider.model}` : ""}
    </span>
  );
}

const providerRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  marginBottom: 14,
  padding: "10px 14px",
  background: "#f5f5f5",
  borderRadius: 6,
  border: "1px solid #e8e8e8",
  flexWrap: "wrap",
};

const providerBtn: React.CSSProperties = {
  padding: "4px 12px",
  border: "1px solid #ccc",
  borderRadius: 20,
  cursor: "pointer",
  background: "#fff",
  fontSize: 12,
  color: "#333",
  transition: "all 0.15s",
};

const providerBtnActive: React.CSSProperties = {
  background: "#0B0B0B",
  color: "#81FBA5",
  borderColor: "#0B0B0B",
  fontWeight: 600,
};

const providerBtnDisabled: React.CSSProperties = {
  opacity: 0.4,
  cursor: "not-allowed",
  color: "#999",
};

const instructionInput: React.CSSProperties = {
  flex: 1,
  padding: "6px 10px",
  border: "1px solid #ddd",
  borderRadius: 4,
  fontSize: 13,
  minWidth: 200,
};

const primaryBtn: React.CSSProperties = {
  padding: "6px 16px",
  background: "#5C41FF",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
};

const secondaryBtn: React.CSSProperties = {
  padding: "6px 12px",
  background: "#f0f0f0",
  border: "1px solid #ccc",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
};

const narrativeBox: React.CSSProperties = {
  background: "#f9f9f9",
  border: "1px solid #e0e0e0",
  borderRadius: 8,
  padding: 16,
  fontSize: 14,
};
