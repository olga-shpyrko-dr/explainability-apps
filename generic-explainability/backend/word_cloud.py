"""Word-frequency tokenization for the word cloud insight (docs/word-cloud-insight-spec.md).

No I/O here -- keeps this unit-testable in isolation, same split as pipeline.py/cohort.py.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

_WORD_RE = re.compile(r"[a-zA-Z']+")

STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because been
    before being below between both but by can can't cannot could couldn't did didn't do does
    doesn't doing don't down during each few for from further had hadn't has hasn't have
    haven't having he he'd he'll he's her here here's hers herself him himself his how
    how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most
    mustn't my myself no nor not of off on once only or other ought our ours ourselves out
    over own same shan't she she'd she'll she's should shouldn't so some such than that
    that's the their theirs them themselves then there there's these they they'd they'll
    they're they've this those through to too under until up very was wasn't we we'd we'll
    we're we've were weren't what what's when when's where where's which while who who's
    whom why why's with won't would wouldn't you you'd you'll you're you've your yours
    yourself yourselves
    """.split()
)

MIN_WORD_LENGTH = 3

# High-cardinality string columns are often IDs, names, or dates (e.g. "TXN00000002",
# "Jessica Montez") rather than genuine free text -- those average 1-2 whitespace tokens
# per value, while real prose (claim descriptions, notes) averages dozens. Distinguishing
# the two keeps IDs out of the word-cloud column picker.
FREE_TEXT_MIN_AVG_WORDS = 4
_SAMPLE_SIZE = 50

# EXPLANATION_{rank}_* columns hold whichever feature landed at that SHAP rank for a given
# row, so a single column mixes values from many unrelated source features (numbers,
# categories, occasional text) row by row. Never real prose -- exclude regardless of what
# any sampled batch of values happens to look like.
_EXPLANATION_COL_RE = re.compile(r"^EXPLANATION_\d+_", re.IGNORECASE)


def looks_like_free_text(column_name: str, values: Iterable[str]) -> bool:
    if _EXPLANATION_COL_RE.match(column_name):
        return False
    sample = [v for v in values if v][:_SAMPLE_SIZE]
    if not sample:
        return False
    avg_words = sum(len(v.split()) for v in sample) / len(sample)
    return avg_words >= FREE_TEXT_MIN_AVG_WORDS


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if len(w) >= MIN_WORD_LENGTH]


def word_frequencies(
    texts: Iterable[str | None], *, min_frequency: int = 1, limit: int = 100
) -> list[tuple[str, int]]:
    """Tally word counts across ``texts``, dropping stopwords and anything below
    ``min_frequency``, returning the top ``limit`` by count (ties broken alphabetically)."""
    counts: Counter[str] = Counter()
    for text in texts:
        if not text:
            continue
        counts.update(w for w in tokenize(text) if w not in STOPWORDS)

    items = [(word, count) for word, count in counts.items() if count >= min_frequency]
    items.sort(key=lambda item: (-item[1], item[0]))
    return items[:limit]
