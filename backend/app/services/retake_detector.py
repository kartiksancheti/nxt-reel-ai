"""
Retake Detector.

Talking-head recordings almost always include retakes: the creator
messes up a line, immediately re-records it, and keeps going. Without
this step, every retake reads as ordinary speech to the rest of the
pipeline — the final cut would include the same line repeated 2-3
times, since our jump-cut logic only removes silence, not duplicate
content.

This runs BEFORE the CutPlan/jump-cut logic in the render pipeline. It
looks for segments that are near-duplicates of each other within a
short window, and keeps only the LAST occurrence — the "last take"
rule: creators re-record until they're happy with a line, so the final
attempt is the one to keep.

Three independent signals, any one of which is enough to flag a retake:
  1. Text similarity (rapidfuzz token_sort_ratio) — near-identical wording
  2. Keyword overlap coefficient — same core content, different phrasing
  3. Partial containment — a false start whose opening words reappear at
     the start of a later, more complete segment
"""
import logging

from rapidfuzz import fuzz

from app.models.timeline import Segment

logger = logging.getLogger(__name__)

WINDOW = 6
TEXT_SIMILARITY_THRESHOLD = 60
KEYWORD_OVERLAP_THRESHOLD = 0.60
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "and",
    "in", "it", "i", "you", "that", "this", "so", "just",
}


def _keyword_set(text: str) -> set[str]:
    words = {w.strip(".,!?").lower() for w in text.split()}
    return words - STOPWORDS


def _keyword_overlap(a: str, b: str) -> float:
    set_a, set_b = _keyword_set(a), _keyword_set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / min(len(set_a), len(set_b))


def _is_partial_containment(a: str, b: str) -> bool:
    a_words = a.strip().split()
    b_words = b.strip().split()
    if len(a_words) < 2 or len(a_words) > len(b_words):
        return False
    prefix_len = min(len(a_words), 6)
    a_start = " ".join(a_words[:prefix_len]).lower()
    b_start = " ".join(b_words[:prefix_len]).lower()
    return fuzz.ratio(a_start, b_start) > 75


def detect_and_filter_retakes(segments: list[Segment]) -> list[Segment]:
    if len(segments) < 2:
        return segments

    to_drop: set[int] = set()

    for i in range(len(segments)):
        if i in to_drop:
            continue
        for j in range(i + 1, min(i + 1 + WINDOW, len(segments))):
            if j in to_drop:
                continue
            text_i, text_j = segments[i].text.strip(), segments[j].text.strip()
            if not text_i or not text_j:
                continue

            similarity = fuzz.token_sort_ratio(text_i, text_j)
            overlap = _keyword_overlap(text_i, text_j)
            contained = _is_partial_containment(text_i, text_j)

            if (
                similarity > TEXT_SIMILARITY_THRESHOLD
                or overlap > KEYWORD_OVERLAP_THRESHOLD
                or contained
            ):
                logger.info(
                    "Retake detected: dropping segment=%s ('%s...') — "
                    "superseded by segment=%s ('%s...') "
                    "[similarity=%.0f overlap=%.2f contained=%s]",
                    segments[i].id, text_i[:40], segments[j].id, text_j[:40],
                    similarity, overlap, contained,
                )
                to_drop.add(i)
                break

    kept = [s for idx, s in enumerate(segments) if idx not in to_drop]
    if to_drop:
        logger.info(
            "Retake detector: dropped %d/%d segments as retakes",
            len(to_drop), len(segments),
        )
    return kept
