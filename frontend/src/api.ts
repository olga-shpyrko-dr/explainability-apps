import axios from "axios";

// Empty string = same-origin (production/Codespace). Override with VITE_API_URL for local dev.
const BASE = import.meta.env.VITE_API_URL ?? "";

export const api = axios.create({ baseURL: BASE });

export interface CohortProfile {
  n_rows: number;
  n_total: number;
  pct_of_total: number;
  score_stats: { mean: number; median: number; p90: number };
  score_stats_full: { mean: number; median: number; p90: number };
  score_histogram: { bin_start: number; bin_end: number; count: number }[];
}

export interface FeatureStat {
  feature_name: string;
  avg_shap: number;
  n_rows: number;
}

export interface GroupStat {
  feature_group: string;
  avg_abs_shap: number;  // bar height — mean(|shap|), preserves signal when features cancel
  sum_shap: number;      // net direction — drives colour; weighted by strength not feature count
  n_rows_with_coverage: number;
  coverage_pct: number;
  top_features: FeatureStat[];
}

export interface WaterfallEntry {
  explanation_rank: number;
  feature_name: string;
  shap_strength: number;
  actual_value: string;
  qualitative_strength: string;
  feature_group: string;
}

export interface RowExplanation {
  row_id: string;
  prediction: number;
  waterfall: WaterfallEntry[];
}

export interface ColumnMeta {
  name: string;
  type: "numeric" | "categorical" | "text";
  min?: number;
  max?: number;
  values?: string[];
  n_unique?: number;
}

export const fetchCohort = (filters: Record<string, unknown>) =>
  api
    .get<CohortProfile>("/api/cohort", {
      params: { filters: JSON.stringify(filters) },
    })
    .then((r) => r.data);

export const fetchGroups = (filters: Record<string, unknown>) =>
  api
    .get<{ n_rows: number; groups: GroupStat[] }>("/api/groups", {
      params: { filters: JSON.stringify(filters) },
    })
    .then((r) => r.data);

export const fetchRow = (rowId: string) =>
  api.get<RowExplanation>(`/api/row/${rowId}`).then((r) => r.data);

export const fetchColumns = () =>
  api.get<{ columns: ColumnMeta[] }>("/api/columns").then((r) => r.data.columns);

export interface LLMProviderInfo {
  id: string;
  name: string;
  available: boolean;
  model: string;
  notes: string;
}

export interface LLMProvidersResponse {
  providers: LLMProviderInfo[];
  default: string;
}

export const fetchLLMProviders = () =>
  api.get<LLMProvidersResponse>("/api/llm/providers").then((r) => r.data);

export const postNarrative = (
  filters: Record<string, unknown>,
  customInstruction = "",
  includeOutcomeRate = false,
  provider?: string,
) =>
  api
    .post<{ narrative: string; provider_used: string; disclaimer: string }>("/api/narrative", {
      filters,
      custom_instruction: customInstruction,
      include_outcome_rate: includeOutcomeRate,
      provider: provider ?? null,
    })
    .then((r) => r.data);
