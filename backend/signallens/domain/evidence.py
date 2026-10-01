"""Deterministic evidence rules (spec review C4).

A model never decides that something is "Confirmed". Models only (a) copy a quote from a
document the agent actually retrieved and (b) label the quote's stance. Everything below
is plain code, so every status is reproducible and explainable to a user.

Rubric, evaluated in order:

- **conflicting**   primary sources disagree; or a primary source contradicts the claim;
                    or independent sources both support and contradict it
- **confirmed**     at least one primary source supports it
- **corroborated**  no primary source, but >= 2 independent origins support it, none contradict
- **single_source** exactly one independent origin supports it
- **unverified**    no verified supporting evidence

Only evidence whose quote was verified against the retrieved text counts. Syndicated
copies (near-identical long quotes on different sites) count as one origin, and
publishers the user has flagged as unreliable (a learned rule) never count.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from signallens.util.text import normalize_for_match
from signallens.util.urls import domain_matches, publisher_key

# Primary for any claim that involves them: regulators, exchanges and statutory registries.
DEFAULT_PRIMARY_REGISTRIES = (
    "rbi.org.in", "sebi.gov.in", "npci.org.in", "mca.gov.in", "irdai.gov.in", "pfrda.org.in",
    "bseindia.com", "nseindia.com", "cdsco.gov.in", "ipindia.gov.in", "meity.gov.in", "pib.gov.in",
    "egazette.gov.in", "sec.gov", "fda.gov", "clinicaltrials.gov", "uspto.gov", "ftc.gov",
    "federalregister.gov", "europa.eu", "fca.org.uk", "mas.gov.sg",
)

# Social platforms and content aggregators: useful leads, never counted as corroboration.
COMMUNITY_DOMAINS = (
    "reddit.com", "x.com", "twitter.com", "facebook.com", "instagram.com", "linkedin.com",
    "quora.com", "medium.com", "youtube.com", "threads.net", "t.me", "ycombinator.com",
    "msn.com", "yahoo.com", "flipboard.com", "newsbreak.com", "dailyhunt.in", "inshorts.com",
    "google.com", "bing.com",
)

SYNDICATION_MIN_CHARS = 60
SYNDICATION_SIMILARITY = 92


@dataclass(frozen=True)
class EvidenceItem:
    source_class: str  # primary | independent | community
    stance: str  # supports | contradicts | context
    publisher: str
    quote: str
    quote_verified: bool
    url: str = ""
    is_archive: bool = False


@dataclass
class EvidenceAssessment:
    status: str
    summary: str
    primary_supporting: list[str] = field(default_factory=list)
    independent_supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def classify_source(
    url: str,
    *,
    entity_domains: Iterable[str] = (),
    regulator_domains: Iterable[str] = (),
    distrusted_publishers: Iterable[str] = (),
) -> str:
    """Primary / independent / community for a URL relative to the entities in a claim.

    ``entity_domains`` are the official domains of every entity the claim is about
    (subject and counterparties): a partner confirming a partnership is primary too.
    """
    if url.startswith("sandbox://"):
        return "primary"  # demo-lab pages stand in for an entity's own site
    publisher = publisher_key(url)
    if publisher in set(distrusted_publishers):
        return "community"
    if domain_matches(url, entity_domains) or domain_matches(url, regulator_domains):
        return "primary"
    if domain_matches(url, DEFAULT_PRIMARY_REGISTRIES):
        return "primary"
    if domain_matches(url, COMMUNITY_DOMAINS):
        return "community"
    return "independent"


def _origins(items: list[EvidenceItem]) -> list[set[str]]:
    """Group supporting items into independent origins.

    Items from the same publisher are one origin. Two publishers whose long quotes are
    near-identical are treated as one origin (syndicated wire copy).
    """
    by_publisher: dict[str, list[str]] = {}
    for item in items:
        by_publisher.setdefault(item.publisher, []).append(normalize_for_match(item.quote))

    publishers = list(by_publisher)
    parent = {p: p for p in publishers}

    def find(p: str) -> str:
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    for i, a in enumerate(publishers):
        for b in publishers[i + 1:]:
            if find(a) == find(b):
                continue
            if any(
                len(qa) >= SYNDICATION_MIN_CHARS
                and len(qb) >= SYNDICATION_MIN_CHARS
                and fuzz.ratio(qa, qb) >= SYNDICATION_SIMILARITY
                for qa in by_publisher[a]
                for qb in by_publisher[b]
            ):
                parent[find(b)] = find(a)

    groups: dict[str, set[str]] = {}
    for p in publishers:
        groups.setdefault(find(p), set()).add(p)
    return sorted(groups.values(), key=lambda g: sorted(g)[0])


def _names(groups: list[set[str]]) -> list[str]:
    return [" / ".join(sorted(g)) for g in groups]


def assess(items: Iterable[EvidenceItem], *, distrusted_publishers: Iterable[str] = ()) -> EvidenceAssessment:
    items = list(items)
    distrusted = set(distrusted_publishers)
    usable = [i for i in items if i.quote_verified and i.stance in ("supports", "contradicts")]

    def cls(item: EvidenceItem) -> str:
        return "community" if item.publisher in distrusted else item.source_class

    prim_sup = [i for i in usable if cls(i) == "primary" and i.stance == "supports"]
    prim_con = [i for i in usable if cls(i) == "primary" and i.stance == "contradicts"]
    ind_sup = _origins([i for i in usable if cls(i) == "independent" and i.stance == "supports"])
    ind_con = _origins([i for i in usable if cls(i) == "independent" and i.stance == "contradicts"])

    prim_sup_names = sorted({i.publisher for i in prim_sup})
    prim_con_names = sorted({i.publisher for i in prim_con})
    sup_names, con_names = _names(ind_sup), _names(ind_con)
    notes: list[str] = []
    if any(i.stance in ("supports", "contradicts") and not i.quote_verified for i in items):
        notes.append("Some quotes could not be verified against the retrieved text and are not counted.")
    if any(i.publisher in distrusted for i in items):
        notes.append("Publishers you marked as unreliable are not counted.")

    base = {"primary_supporting": prim_sup_names, "independent_supporting": sup_names, "notes": notes}

    if prim_sup and prim_con:
        return EvidenceAssessment(
            "conflicting",
            f"Conflicting — official sources disagree ({', '.join(sorted(set(prim_sup_names + prim_con_names)))}).",
            contradicting=prim_con_names,
            **base,
        )
    if prim_sup:
        summary = f"Confirmed — primary source: {', '.join(prim_sup_names)}."
        if sup_names:
            summary += f" Also reported by {', '.join(sup_names)}."
        if con_names:
            notes.append(f"{len(con_names)} secondary source(s) report otherwise: {', '.join(con_names)}.")
        return EvidenceAssessment("confirmed", summary, contradicting=con_names, **base)
    if prim_con:
        return EvidenceAssessment(
            "conflicting",
            f"Conflicting — {', '.join(prim_con_names)} (official) contradicts "
            f"{', '.join(sup_names) or 'the report'}.",
            contradicting=prim_con_names,
            **base,
        )
    if ind_sup and ind_con:
        return EvidenceAssessment(
            "conflicting",
            f"Conflicting — supported by {', '.join(sup_names)}, contradicted by {', '.join(con_names)}.",
            contradicting=con_names,
            **base,
        )
    if len(ind_sup) >= 2:
        return EvidenceAssessment(
            "corroborated",
            f"Corroborated — {len(ind_sup)} independent publishers: {', '.join(sup_names)}. "
            "No contradicting sources.",
            **base,
        )
    if len(ind_sup) == 1:
        return EvidenceAssessment("single_source", f"Single source — reported only by {sup_names[0]} so far.", **base)
    return EvidenceAssessment("unverified", "Unverified — no retrievable source confirms this yet.", **base)
