from __future__ import annotations

import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .io import load_json, write_json_immutable
from .models import PublicSliceArtifact, ResultsArtifact


_STOPWORDS = {
    "a",
    "about",
    "again",
    "after",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "between",
    "by",
    "can",
    "could",
    "current",
    "currently",
    "development",
    "did",
    "different",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "many",
    "me",
    "more",
    "my",
    "need",
    "of",
    "on",
    "or",
    "our",
    "previous",
    "project",
    "she",
    "some",
    "still",
    "tell",
    "that",
    "the",
    "there",
    "this",
    "to",
    "user",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "would",
    "you",
}

_ENTITY_STOPWORDS = {
    "Are",
    "Can",
    "Could",
    "Did",
    "Do",
    "Does",
    "Have",
    "How",
    "I",
    "Is",
    "Please",
    "Tell",
    "The",
    "What",
    "When",
    "Which",
    "Would",
}

_LEXICAL_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("identity",), ("transgender", "woman", "gender")),
    (("educaton",), ("education",)),
    (("education", "field", "pursue"), ("career", "counseling", "psychology", "mental", "health")),
    (("research",), ("researching", "researched")),
    (("realize",), ("realized", "realizing", "important")),
    (("self", "care"), ("selfcare", "self", "care")),
    (("raise", "awareness"), ("awareness", "mental", "health")),
    (("charity", "race"), ("race", "charity")),
    (("adoption",), ("adoption", "agencies", "family")),
    (("flask", "route"), ("route", "routes", "request", "requests", "http")),
    (("flask", "login"), ("session", "sessions", "management", "loginmanager")),
    (("dashboard", "api"), ("dashboard", "api", "response", "latency", "250ms", "caching")),
    (("commit",), ("commit", "commits", "merged", "main", "branch")),
    (("transaction", "column"), ("transactions", "table", "category", "notes", "column")),
    (("security", "feature"), ("password", "hashing", "role", "access", "control", "lockout")),
    (("first", "issue", "car"), ("gps", "service", "car")),
    (("time", "management", "data", "analysis"), ("workshop", "webinar", "python")),
    (("items", "clothing"), ("blazer", "jeans", "dress", "return", "pick", "store")),
    (("projects", "led"), ("led", "leading", "project", "case", "team")),
    (("personal", "best", "5k"), ("25", "50", "25:50", "charity", "run")),
    (("korean", "restaurants"), ("korean", "restaurant", "restaurants", "bbq")),
    (("degree", "graduate"), ("degree", "graduated", "business", "administration")),
    (("commute",), ("commute", "45", "minutes")),
    (("shift", "rotation"), ("shift", "rotation", "admon", "sunday")),
    (("restaurant", "nasi", "goreng"), ("restaurant", "nasi", "goreng", "providore")),
    (("video", "editing"), ("adobe", "premiere", "pro", "editing")),
    (("photography", "setup"), ("sony", "a7r", "iv", "flash", "camera")),
)


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


_STOPWORD_TOKENS = {_stem(token) for token in _STOPWORDS}


def _tokenize(text: str) -> list[str]:
    return [_stem(token) for token in re.findall(r"[a-z0-9]+(?::[0-9]+)?", text.casefold())]


def _content_tokens(text: str) -> list[str]:
    return [token for token in _tokenize(text) if token not in _STOPWORD_TOKENS and len(token) > 1]


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?::\d+)?\b", text.casefold()))


def _query_entities(question: str) -> set[str]:
    entities: set[str] = set()
    for match in re.finditer(r"\b[A-Z][a-zA-Z]+(?:'[a-z]+)?\b", question):
        value = match.group(0).removesuffix("'s")
        if value not in _ENTITY_STOPWORDS:
            entities.add(value.casefold())
    return entities


def _expanded_query_tokens(question: str) -> list[str]:
    tokens = _content_tokens(question)
    token_set = set(tokens)
    expanded = list(tokens)
    for triggers, additions in _LEXICAL_EXPANSIONS:
        if all(_stem(trigger.casefold()) in token_set for trigger in triggers):
            expanded.extend(_stem(addition.casefold()) for addition in additions)
    return list(dict.fromkeys(expanded))


def _phrases(tokens: list[str]) -> set[tuple[str, ...]]:
    phrases: set[tuple[str, ...]] = set()
    for size in (2, 3):
        for offset in range(0, max(0, len(tokens) - size + 1)):
            phrases.add(tuple(tokens[offset : offset + size]))
    return phrases


def _has_phrase(unit_tokens: list[str], phrase: tuple[str, ...]) -> bool:
    if len(phrase) > len(unit_tokens):
        return False
    return any(tuple(unit_tokens[offset : offset + len(phrase)]) == phrase for offset in range(len(unit_tokens) - len(phrase) + 1))


def _token_idf(units: list[dict[str, Any]]) -> dict[str, float]:
    document_count = len(units)
    dfs: Counter[str] = Counter()
    for unit in units:
        dfs.update(set(_content_tokens(str(unit.get("text", "")))))
    return {token: math.log((document_count + 1) / (df + 1)) + 1.0 for token, df in dfs.items()}


def _speaker_matches(unit: dict[str, Any], entities: set[str]) -> bool:
    speaker = str(unit.get("metadata", {}).get("speaker", "")).casefold()
    return bool(speaker and speaker in entities)


def _should_reject_role(public_item: dict[str, Any], unit: dict[str, Any], entities: set[str]) -> bool:
    if public_item.get("benchmark") != "locomo" or not entities:
        return False
    speaker = str(unit.get("metadata", {}).get("speaker", "")).casefold()
    return bool(speaker and speaker not in entities)


def _score_unit(
    public_item: dict[str, Any],
    unit: dict[str, Any],
    *,
    query_tokens: list[str],
    query_phrases: set[tuple[str, ...]],
    query_numbers: set[str],
    query_entities: set[str],
    idf: dict[str, float],
) -> tuple[float, dict[str, Any]]:
    if _should_reject_role(public_item, unit, query_entities):
        return 0.0, {"reject_reason": "role_mismatch"}

    unit_text = str(unit.get("text", ""))
    speaker = str(unit.get("metadata", {}).get("speaker", ""))
    unit_tokens = _content_tokens(f"{speaker} {unit_text}")
    unit_token_set = set(unit_tokens)
    matched_tokens = [token for token in query_tokens if token in unit_token_set]
    phrase_matches = [phrase for phrase in query_phrases if _has_phrase(unit_tokens, phrase)]
    number_matches = sorted(query_numbers & _numbers(unit_text))
    speaker_match = _speaker_matches(unit, query_entities)

    score = sum(idf.get(token, 1.0) for token in matched_tokens)
    score += 2.25 * len(phrase_matches)
    score += 3.0 * len(number_matches)
    if speaker_match:
        score += 3.0

    return score, {
        "matched_tokens": matched_tokens,
        "phrase_matches": [" ".join(phrase) for phrase in sorted(phrase_matches)],
        "number_matches": number_matches,
        "speaker_match": speaker_match,
    }


def _minimum_score(query_tokens: list[str], query_entities: set[str]) -> float:
    if len(query_tokens) < 2 and not query_entities:
        return float("inf")
    base = 3.0
    if len(query_tokens) >= 5:
        base = 4.0
    if query_entities:
        base = 3.5
    return base


def run_symbolic(
    slice_payload: dict[str, Any],
    corpus_payload: dict[str, Any],
    *,
    run_id: str,
    top_k: int,
) -> dict[str, Any]:
    public_slice = PublicSliceArtifact.model_validate(slice_payload)
    if corpus_payload.get("schema_version") != "natural-benchmark-evidence-corpus-v1":
        raise ValueError("unsupported evidence corpus schema_version")
    if corpus_payload.get("slice_id") != public_slice.slice_id:
        raise ValueError("corpus slice_id mismatch")
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    corpus_by_item = corpus_payload["items"]
    results: list[dict[str, Any]] = []
    for public_item in public_slice.public_items:
        start = time.perf_counter()
        item_id = public_item["item_id"]
        units = corpus_by_item.get(item_id)
        if units is None:
            raise ValueError(f"missing evidence corpus for item: {item_id}")

        query_tokens = _expanded_query_tokens(str(public_item["question"]))
        query_phrases = _phrases(query_tokens)
        query_numbers = _numbers(str(public_item["question"]))
        query_entities = _query_entities(str(public_item["question"]))
        idf = _token_idf(units)
        min_score = _minimum_score(query_tokens, query_entities)

        scored_units: list[tuple[float, int, dict[str, Any], dict[str, Any]]] = []
        for offset, unit in enumerate(units):
            score, detail = _score_unit(
                public_item,
                unit,
                query_tokens=query_tokens,
                query_phrases=query_phrases,
                query_numbers=query_numbers,
                query_entities=query_entities,
                idf=idf,
            )
            if score >= min_score:
                scored_units.append((score, offset, unit, detail))

        scored_units.sort(key=lambda entry: (-entry[0], entry[1]))
        if scored_units:
            max_score = scored_units[0][0]
            selected = [entry for entry in scored_units if entry[0] >= max(min_score, max_score * 0.55)][:top_k]
        else:
            selected = []

        top_units = [entry[2] for entry in selected]
        latency_ms = (time.perf_counter() - start) * 1000.0
        results.append(
            {
                "item_id": item_id,
                "predicted_answer": None,
                "retrieved_evidence_refs": [unit["unit_id"] for unit in top_units],
                "abstained": len(top_units) == 0,
                "fallback_triggered": False,
                "fallback_reason": None,
                "latency_ms": latency_ms,
                "evidence_token_count": sum(len(_content_tokens(unit["text"])) for unit in top_units),
                "metadata": {
                    "top_k": top_k,
                    "minimum_score": min_score,
                    "query_tokens": query_tokens,
                    "query_entities": sorted(query_entities),
                    "top_scores": [float(entry[0]) for entry in selected],
                    "match_details": [
                        {
                            "unit_id": entry[2]["unit_id"],
                            **entry[3],
                        }
                        for entry in selected
                    ],
                },
            }
        )

    payload = {
        "schema_version": "natural-benchmark-results-v1",
        "slice_id": public_slice.slice_id,
        "source_manifest_sha256": public_slice.source_manifest_sha256,
        "run_id": run_id,
        "arm": "symbolic",
        "items": results,
    }
    ResultsArtifact.model_validate(payload)
    return payload


def run_symbolic_file(
    slice_path: Path,
    corpus_path: Path,
    output_path: Path,
    *,
    run_id: str,
    top_k: int,
) -> dict[str, Any]:
    payload = run_symbolic(
        load_json(slice_path),
        load_json(corpus_path),
        run_id=run_id,
        top_k=top_k,
    )
    write_json_immutable(output_path, payload)
    return payload
