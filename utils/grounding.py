"""
Numeric grounding check for LLM-written commentary.

Execution 2 produced the line "whale influence is approximately 47.31%",
derived from an invented formula. The figure was fabricated but read as
authoritative — the worst failure mode for a trading note.

This extracts every number an LLM wrote and verifies each one appears in
the source data it was given. Anything citing a number that was never in
the input is rejected. The check is deliberately one-directional: it does
not try to judge whether the prose is *reasoning* well, only whether it is
inventing figures.
"""

import re

NUMBER_RE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
# Small integers are ordinary prose ("two reasons", "1 contract") and would
# produce constant false positives.
IGNORE_BELOW = 10.0


def extract_numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(text or "")


def _canon(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def ungrounded_numbers(commentary: str, source: str,
                        tolerance: float = 0.01) -> list[str]:
    """Numbers in `commentary` that do not appear in `source`.

    A value matches if it appears literally, or within `tolerance` relative
    difference of some number in the source — rounding (30.45 -> 30.5) is
    legitimate, invention is not.
    """
    src_values = [v for v in (_canon(t) for t in extract_numbers(source)) if v is not None]
    bad = []

    for token in extract_numbers(commentary):
        value = _canon(token)
        if value is None or abs(value) < IGNORE_BELOW:
            continue
        for sv in src_values:
            if sv == value:
                break
            denom = max(abs(sv), abs(value), 1e-9)
            if abs(sv - value) / denom <= tolerance:
                break
        else:
            bad.append(token)
    return bad


def is_grounded(commentary: str, source: str) -> bool:
    return not ungrounded_numbers(commentary, source)


def vet_commentary(commentary: str, source: str) -> tuple[str, list[str]]:
    """Returns (safe_commentary, rejected_numbers).

    Rejection drops the whole note rather than editing it: a sentence with
    its fabricated figure surgically removed still carries the fabricated
    reasoning that produced it.
    """
    bad = ungrounded_numbers(commentary, source)
    return ("" if bad else commentary), bad
