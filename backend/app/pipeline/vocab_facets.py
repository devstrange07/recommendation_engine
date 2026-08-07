"""Facet value alias → canonical helpers for vocab/facets/*.yaml."""

from __future__ import annotations

import re

from app.schemas import Facet, Flag, NormalizationRecord, Normalized, StagedProduct


def _domain_root(category_path: str) -> str:
    return (category_path or "").split("/")[0]


def _facet_def(vocab: dict, category_path: str, key: str) -> dict | None:
    schemas = vocab.get("facet_schemas") or {}
    for facet in schemas.get(_domain_root(category_path)) or []:
        if str(facet.get("key")) == key:
            return facet
    return None


def alias_lookup(vocab: dict, category_path: str, key: str) -> dict[str, str]:
    """Map lowercased alias/value → canonical string for a facet."""
    return {alias.lower(): canon for alias, canon in alias_entries(vocab, category_path, key)}


def alias_entries(vocab: dict, category_path: str, key: str) -> list[tuple[str, str]]:
    """(alias_or_value, canonical) pairs, longest first. Preserves YAML alias casing."""
    facet = _facet_def(vocab, category_path, key)
    if not facet:
        return []
    by_lower: dict[str, tuple[str, str]] = {}
    for value in facet.get("values") or []:
        token = str(value)
        by_lower[token.lower()] = (token, token)
    aliases = facet.get("aliases") or {}
    if isinstance(aliases, dict):
        for alias, canonical in aliases.items():
            token = str(alias)
            by_lower[token.lower()] = (token, str(canonical))
    entries = list(by_lower.values())
    entries.sort(key=lambda item: len(item[0]), reverse=True)
    return entries


def resolve_facet_value(
    vocab: dict, category_path: str, key: str, raw: str | float | int | bool
) -> str | float | int | bool:
    if not isinstance(raw, str):
        return raw
    lookup = alias_lookup(vocab, category_path, key)
    if not lookup:
        return raw
    return lookup.get(raw.strip().lower(), raw)


def match_canonical_from_entries(text: str, entries: list[tuple[str, str]]) -> str | None:
    """Longest alias/value wins. Aliases with length <= 2 are case-sensitive."""
    if not text or not entries:
        return None
    for alias, canon in entries:
        if len(alias) <= 2:
            if re.search(rf"\b{re.escape(alias)}\b", text):
                return canon
            continue
        if re.search(rf"\b{re.escape(alias)}\b", text, flags=re.IGNORECASE):
            return canon
    return None


def staged_text_blob(staged: StagedProduct) -> str:
    return " ".join(
        [
            staged.name or "",
            staged.description_text or "",
            " ".join(p.feature_text or "" for p in staged.plans),
        ]
    )


def _flag_facet_key(field: str) -> str:
    field = (field or "").strip()
    if field.startswith("facets."):
        return field.split(".", 1)[1]
    return field


def apply_facet_aliases(
    record: NormalizationRecord,
    vocab: dict,
    staged: StagedProduct | None = None,
) -> NormalizationRecord:
    """Canonicalize facet values; drop ambiguous_attribute when text uniquely aliases."""
    n = record.normalized
    category_path = n.category_path
    by_key: dict[str, Facet] = {}
    order: list[str] = []
    for facet in n.facets:
        resolved = Facet(
            key=facet.key,
            value=resolve_facet_value(vocab, category_path, facet.key, facet.value),
            unit=facet.unit,
        )
        if resolved.key not in by_key:
            order.append(resolved.key)
        by_key[resolved.key] = resolved

    text = staged_text_blob(staged) if staged else ""
    kept_flags: list[Flag] = []
    for flag in record.flags:
        if flag.type != "ambiguous_attribute":
            kept_flags.append(flag)
            continue
        key = _flag_facet_key(flag.field)
        entries = alias_entries(vocab, category_path, key)
        if not entries or not text:
            kept_flags.append(flag)
            continue
        canonical = match_canonical_from_entries(text, entries)
        if canonical is None:
            kept_flags.append(flag)
            continue
        prev = by_key.get(key)
        if key not in by_key:
            order.append(key)
        by_key[key] = Facet(key=key, value=canonical, unit=prev.unit if prev else None)

    return NormalizationRecord(
        product_id=record.product_id,
        schema_version=record.schema_version,
        normalized=Normalized(
            clean_description=n.clean_description,
            short_pitch=n.short_pitch,
            category_path=n.category_path,
            use_case_tags=n.use_case_tags,
            target_audience=n.target_audience,
            aliases=n.aliases,
            plan_features=n.plan_features,
            kind=n.kind,
            brand=n.brand,
            facets=[by_key[k] for k in order],
        ),
        confidence=record.confidence,
        flags=kept_flags,
    )
