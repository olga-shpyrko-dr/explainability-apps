import axios from "axios";

const BASE = import.meta.env.VITE_API_URL ?? "";

export const api = axios.create({ baseURL: BASE });

// ---------------------------------------------------------------------------
// App config (from /api/config — loaded once at frontend startup)
// ---------------------------------------------------------------------------

export interface ProfileAttribute {
  column: string;
  display_name: string;
  filter_type: "range" | "multiselect" | "toggle";
  show_in_profile: boolean;
}

export interface AppConfig {
  app_title: string;
  app_subtitle: string;
  row_id_col: string;
  prediction_col: string;
  max_explanations: number;
  // Narrative labels
  entity_label: string;
  entity_label_plural: string;
  high_score_label: string;
  low_score_label: string;
  factor_positive_label: string;
  factor_negative_label: string;
  // Filter / profile config
  profile_attributes: ProfileAttribute[];
  score_filter: { show: boolean; display_name: string };
  top_explanation_filter: { show: boolean; display_name: string; explanation_slot: number };
  feature_groups: string[];
  // Dataset selector
  current_dataset_id: string | null;
  current_dataset_name: string | null;
  dataset_selector_enabled: boolean;
}

export interface DatasetInfo {
  id: string;
  name: string;
}

export const fetchAppConfig = () =>
  api.get<AppConfig>("/api/config").then((r) => r.data);

// ---------------------------------------------------------------------------
// Cohort and explanation types
// ---------------------------------------------------------------------------

export interface CohortProfile {
  n_rows: number;
  n_total: number;
  pct_of_total: number;
  score_stats: { mean: number; median: number; p90: number };
  score_stats_full: { mean: number; median: number; p90: number };
  score_histogram: { bin_start: number; bin_end: number; count: number }[];
  sample_row_ids: string[];
}

export interface FeatureStat {
  feature_name: string;
  avg_shap: number;
  avg_abs_shap: number;
  n_rows: number;
}

export interface GroupStat {
  feature_group: string;
  avg_abs_shap: number;  // bar height — mean(|shap|)
  avg_shap: number;      // signed average — used in narrative table
  sum_shap: number;      // net direction — drives colour
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

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export const fetchCohort = (filters: Record<string, unknown>) =>
  api
    .get<CohortProfile>("/api/cohort", { params: { filters: JSON.stringify(filters) } })
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

export const fetchLLMProviders = () =>
  api.get<LLMProvidersResponse>("/api/llm/providers").then((r) => r.data);

export const fetchDatasets = () =>
  api
    .get<{ datasets: DatasetInfo[]; use_case_mode: boolean }>("/api/datasets")
    .then((r) => r.data);

export const switchDataset = (dataset_id: string, display_name?: string) =>
  api
    .post<{ dataset_id: string; dataset_name: string; rows_loaded: number }>("/api/dataset/switch", {
      dataset_id,
      display_name: display_name || null,
    })
    .then((r) => r.data);

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

export const postRowNarrative = (
  rowId: string,
  customInstruction = "",
  provider?: string,
) =>
  api
    .post<{ narrative: string; provider_used: string; disclaimer: string }>("/api/narrative/row", {
      row_id: rowId,
      custom_instruction: customInstruction,
      provider: provider ?? null,
    })
    .then((r) => r.data);
