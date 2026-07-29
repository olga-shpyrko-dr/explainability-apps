# Word Cloud Insight — Mini Spec

**Reference implementation:** `docs/word-cloud-files.zip` (a chatbot-observability app's prompt/response
word-frequency cloud). Ports the same algorithm and rendering approach to this app's domain: instead of
chat `prompt`/`response` fields, the target is any free-text **feature column** in the scored population.

## 1. Goal

Show the most common words in a free-text column **for the currently filtered cohort**, so users can spot
vocabulary patterns correlated with a segment (e.g. common terms in claim descriptions for high-score rows)
without reading rows one at a time.

## 2. Scope

- In scope: one text column at a time, word-frequency cloud + table view, driven by the existing cohort
  filters (same `filters` state already used by Group Explanations).
- Out of scope for v1: n-grams/phrases, sentiment, per-word SHAP attribution, cross-column comparison, and
  showing a cloud on the Individual Row tab (a single row's text value isn't meaningful as a "cloud").

## 3. Which columns qualify

No new config needed. `/api/columns` (`backend/main.py:368-393`) already tags any non-numeric column with
`n_unique > 200` as `type: "text"` — reuse that as-is. The new tab only appears when at least one column has
`type === "text"`; a picker lets the user choose among them if there's more than one.

## 4. Backend

### 4.1 `backend/word_cloud.py` (new module — pure functions, mirrors `patterns.py` from the reference)

Port `tokenize` / `word_frequencies` essentially unchanged:

- `_WORD_RE = re.compile(r"[a-zA-Z']+")`, lowercase, `MIN_WORD_LENGTH = 3`.
- Same general-English `STOPWORDS` frozenset — drop the reference's chat-specific filler terms
  (`please/thanks/hi/hello/ok/okay/yes`), since this app isn't scoring chat transcripts.
- `word_frequencies(texts, min_frequency=1, limit=100) -> list[tuple[str, int]]` — unchanged signature.

Kept as a standalone module with no I/O, same reasoning as the reference: unit-testable in isolation.

### 4.2 New endpoint — `GET /api/wordcloud`

```
Query params:
  column         required — must be a column with type == "text" per /api/columns
  filters        optional JSON, same shape as /api/cohort & /api/groups
  min_frequency  optional int, default 2
  limit          optional int, default 100

Response:
  {"column": str, "n_rows": int, "words": [{"word": str, "count": int}, ...]}
```

Follows the existing `/api/groups` pattern in `main.py`:

```python
@app.get("/api/wordcloud")
def get_wordcloud(
    column: str,
    filters: Optional[str] = Query(None),
    min_frequency: int = 2,
    limit: int = 100,
):
    df = _pop()
    cohort_df = apply_filters(df, _parse_filters(filters))
    if column not in cohort_df.columns:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found")
    words = word_frequencies(cohort_df[column].astype(str), min_frequency=min_frequency, limit=limit)
    return {
        "column": column,
        "n_rows": len(cohort_df),
        "words": [{"word": w, "count": c} for w, c in words],
    }
```

No caching or background job — tokenizing a cohort-sized slice is cheap and simply reruns on every filter
change, same as `/api/cohort` and `/api/groups` already do.

## 5. Frontend

### 5.1 `api.ts` — new type + fetch helper

```ts
export interface WordFrequency { word: string; count: number }

export const fetchWordCloud = (column: string, filters: Record<string, unknown>, minFrequency = 2) =>
  api.get<{ column: string; n_rows: number; words: WordFrequency[] }>("/api/wordcloud", {
    params: { column, filters: JSON.stringify(filters), min_frequency: minFrequency },
  }).then((r) => r.data);
```

### 5.2 `components/WordCloud.tsx` (ported, restyled to this app's plain inline-style system)

Keep the reference's core algorithm (`fontSizeFor`: linear interpolation between `MIN_FONT_PX`/`MAX_FONT_PX`
by word count), but adapt to match this codebase rather than the reference's stack:

- No shadcn `Tooltip`/Tailwind here (this app uses plain inline `style={}` objects and `recharts` only for
  charts) — use a plain `title` attribute on each word span for the hover count, same low-tech approach the
  rest of this app uses outside of `recharts` components.
- Single brand color for all words (indigo `#5C41FF`, matching `primaryBtn`) — magnitude is encoded by size
  only, never by hue, per the dataviz guidance the reference already followed.
- Keep `role="list"`/`role="listitem"` + `tabIndex` for accessibility.

### 5.3 `components/WordCloudPanel.tsx` (ported, no react-query)

This app has no data-fetching library — components either lift state to `App.tsx` (like `groups`/`profile`)
or self-fetch with `useState`/`useEffect` (like `DatasetSelector`). Since word-cloud data isn't needed by any
sibling component, make the panel self-contained: it owns `column`, `minFrequency`, `view` state and fetches
on change (debounced like `App.tsx`'s existing 400ms `refresh`).

- Column picker: `<select>` populated from `/api/columns` entries where `type === "text"` (generalizes the
  reference's hardcoded prompt/response toggle to N columns).
- Min-frequency input + Cloud/Table view toggle, same as the reference.
- Loading/empty copy matching this app's existing tone ("Loading…", "No words match the current filters.").

### 5.4 Wiring into `App.tsx`

- `type Tab = "groups" | "row" | "text"`.
- Fetch `/api/columns` once at startup (via the already-defined but currently-unused `fetchColumns()` in
  `api.ts`) into a new `columns` state.
- Add the tab to `TABS` only when `columns.some((c) => c.type === "text")`.
- Panel receives the current `filters` state, same wiring as `GroupExplanationChart`/`InlineNarrative`.
- New card in the tab body: `cardStyle` wrapper, `cardEyebrow` reading e.g. `TEXT WORD FREQUENCY — {COLUMN}`.

## 6. Open questions

1. **Tab label** — generic "Word Insights", or something derived from config (this app already lets
   `entity_label` drive the "Individual Row" tab name)?
2. **Column picker UX** — plain `<select>` is fine for now; only worth revisiting if a deployment has many
   text columns and users want them grouped/labeled.
3. **Stopwords** — keep the reference's hardcoded general-English list for v1. Revisit only if a real
   deployment needs domain-specific exclusions (e.g. boilerplate phrases in claim notes).
4. **Min-frequency / limit controls** — expose in the UI (as the reference does) or fix as constants for v1?
   Leaning toward exposing min-frequency only, since it's the one users are likely to tune per cohort size.
