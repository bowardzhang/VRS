#!/usr/bin/env python3
"""Map each country's own (brand, model) registration strings onto the KBA-style
brand/model keys used by ``data/vehicle_specs.csv``.

The supplier configuration in ``vehicle_specs.csv`` is keyed by the German KBA
FZ 10.1 brand/model vocabulary (``VW``/``GOLF``, ``MERCEDES``/``A-KLASSE``,
``HYUNDAI``/``I 10`` …).  Every other market names its models differently —
long-form brands (``VOLKSWAGEN``), market-specific brands (``VAUXHALL`` for
Opel, ``CUPRA`` split out of Seat), brand-prefixed model strings
(``VOLKSWAGEN GOLF``), and English body-class words (``A CLASS`` vs
``A-KLASSE``, ``1 SERIES`` vs ``1ER``).

``resolve(brand, model)`` normalises those differences and returns the matching
``(brand, model)`` config key, or ``None`` when no confident match exists.  It
deliberately errs toward *precision*: an unmatched model is reported as
``Unclassified`` by the caller (and folded into the transparent coverage %),
which is far less harmful than silently attributing the wrong supplier.

The matcher is data-driven off the loaded spec keys, so adding rows to
``vehicle_specs.csv`` automatically widens coverage with no code change.
"""
from __future__ import annotations

import re

# Country brand string (upper-cased) -> canonical KBA/config brand.
BRAND_ALIAS = {
    "VOLKSWAGEN": "VW", "VW": "VW",
    "MERCEDES-BENZ": "MERCEDES", "MERCEDES BENZ": "MERCEDES", "MERCEDES": "MERCEDES",
    "VAUXHALL": "OPEL", "OPEL": "OPEL",          # Vauxhall is the UK marque for Opel
    "CUPRA": "SEAT",                              # config carries Cupra models under Seat
    "SKODA": "SKODA", "ŠKODA": "SKODA",
    "CITROEN": "CITROEN", "CITROËN": "CITROEN",
    "TESLA": "TESLA", "TESLA MOTORS": "TESLA",
    "LAND ROVER": "LAND ROVER", "LANDROVER": "LAND ROVER",
    "MG": "MG ROEWE", "ROEWE": "MG ROEWE", "MG ROEWE": "MG ROEWE",
    "MERCEDES-AMG": "MERCEDES",
}

# Body-class / series suffix words that differ by market but mean the same model
# family (``A CLASS`` == ``A-KLASSE``, ``3 SERIES`` == ``3ER``).  Stripped from
# both sides before comparison.
_SUFFIX_WORDS = {"CLASS", "KLASSE", "SERIES"}

# Small explicit fixups for high-volume models whose strings don't converge under
# the generic rule.  Keyed by (canonical_brand, normalised_model) -> config model.
MODEL_FIXUP = {
    ("BMW", "1"): "1ER", ("BMW", "2"): "2ER", ("BMW", "3"): "3ER",
    ("BMW", "4"): "4ER", ("BMW", "5"): "5ER",
    ("VOLVO", "V60"): "60", ("VOLVO", "S60"): "60", ("VOLVO", "V90"): "60",
    ("RENAULT", "5"): "R5", ("RENAULT", "5ETECHELECTRIC"): "R5",
    ("TOYOTA", "RAV4"): "RAV 4",
}


def _norm_model(s: str) -> str:
    """Collapse a model string to a comparison key: upper-case, split on spaces,
    slashes, hyphens and dots (so ``A-KLASSE`` and ``A CLASS`` converge, and
    ``T-ROC`` normalises the same on both sides), drop body-class suffix words,
    and strip everything but ``A-Z0-9``."""
    toks = [t for t in re.split(r"[\s/.\-]+", s.upper().strip()) if t not in _SUFFIX_WORDS]
    return re.sub(r"[^A-Z0-9]", "", "".join(toks))


class SupplierMatcher:
    """Resolve country (brand, model) strings against loaded spec keys."""

    def __init__(self, spec_keys):
        # spec_keys: iterable of (brand, model) exactly as in vehicle_specs.csv.
        self._exact = set()                         # (BRAND, MODEL) upper
        self._by_norm: dict[tuple[str, str], str] = {}   # (BRAND, norm) -> MODEL
        for brand, model in spec_keys:
            b = brand.strip().upper()
            m = model.strip().upper()
            self._exact.add((b, m))
            self._by_norm.setdefault((b, _norm_model(m)), m)

    def brand(self, brand: str) -> str:
        b = brand.strip().upper()
        return BRAND_ALIAS.get(b, b)

    def resolve(self, brand: str, model: str):
        """Return the config (brand, model) key, or None."""
        cb = self.brand(brand)
        m = model.strip().upper()
        # Drop a leading brand token the country baked into the model string
        # (e.g. "VOLKSWAGEN GOLF", "MG ZS", "TESLA MOTORS MODEL Y"). Try the raw
        # brand, the canonical brand, and any multi-word alias (e.g. "TESLA
        # MOTORS", "MERCEDES-BENZ"); strip the longest prefix that matches.
        prefixes = [brand.strip().upper(), cb, *BRAND_ALIAS.keys()]
        for pref in sorted(prefixes, key=len, reverse=True):
            if pref and m.startswith(pref + " "):
                m = m[len(pref) + 1:].strip()
                break
        if (cb, m) in self._exact:
            return (cb, m)
        nm = _norm_model(m)
        fix = MODEL_FIXUP.get((cb, nm))
        if fix and (cb, fix) in self._exact:
            return (cb, fix)
        hit = self._by_norm.get((cb, nm))
        if hit is not None:
            return (cb, hit)
        # Last resort: first model token (handles "PROACE VERSO" -> "PROACE").
        first = _norm_model(m.split(" ")[0]) if " " in m else None
        if first:
            hit = self._by_norm.get((cb, first))
            if hit is not None:
                return (cb, hit)
        return None
