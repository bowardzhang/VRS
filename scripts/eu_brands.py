"""Shared brand canonicalisation + origin mapping for multi-country aggregation.

Different national registers spell the same marque differently (RDW
"VOLKSWAGEN" vs KBA "VW", "MERCEDES-BENZ" vs "MERCEDES", "LYNK&CO" vs
"LYNK & CO"). ``canonical()`` folds them to one label so brands and origins add
up correctly across countries. ``origin()`` returns the marque's country of
origin (the car's nationality, not the current owner group).
"""
from __future__ import annotations

# Alias -> canonical label (all compared upper-cased, stripped).
ALIASES: dict[str, str] = {
    "VOLKSWAGEN": "VW",
    "VW NUTZFAHRZEUGE": "VW",
    "MERCEDES-BENZ": "MERCEDES",
    "MERCEDES BENZ": "MERCEDES",
    "MERCEDES-AMG": "MERCEDES",
    "ŠKODA": "SKODA",
    "CITROËN": "CITROEN",
    "LYNK&CO": "LYNK & CO",
    "LYNK & CO.": "LYNK & CO",
    "MG ROEWE": "MG",
    "ROEWE": "MG",
    "LAND-ROVER": "LAND ROVER",
    "RANGE ROVER": "LAND ROVER",
    "ALFA-ROMEO": "ALFA ROMEO",
    "ROLLS-ROYCE": "ROLLS ROYCE",
    "ASTON-MARTIN": "ASTON MARTIN",
    "GREAT WALL": "GWM",
    # Traficom (Finland) spellings
    "TESLA MOTORS": "TESLA",
    "BMW I": "BMW",
    "KG MOBILITY": "KGM",
    "OTHERS": "OTHER", "MUU": "OTHER", "MUUT": "OTHER", "OVRIGA": "OTHER",
}

BRAND_ORIGIN: dict[str, str] = {
    # Germany
    "VW": "Germany", "MERCEDES": "Germany", "BMW": "Germany", "AUDI": "Germany",
    "OPEL": "Germany", "PORSCHE": "Germany", "SMART": "Germany", "MAN": "Germany",
    "ALPINA": "Germany", "BORGWARD": "Germany",
    # Czechia / Spain (VW-group marques, kept at marque origin)
    "SKODA": "Czechia", "SEAT": "Spain", "CUPRA": "Spain",
    # France
    "RENAULT": "France", "PEUGEOT": "France", "CITROEN": "France", "DS": "France",
    "ALPINE": "France", "DACIA": "France",
    # Italy
    "FIAT": "Italy", "ALFA ROMEO": "Italy", "FERRARI": "Italy", "MASERATI": "Italy",
    "LANCIA": "Italy", "ABARTH": "Italy", "IVECO": "Italy",
    # Sweden
    "VOLVO": "Sweden", "POLESTAR": "Sweden",
    # United Kingdom
    "MINI": "United Kingdom", "LAND ROVER": "United Kingdom", "JAGUAR": "United Kingdom",
    "BENTLEY": "United Kingdom", "ROLLS ROYCE": "United Kingdom", "LOTUS": "United Kingdom",
    "ASTON MARTIN": "United Kingdom", "MORGAN": "United Kingdom", "INEOS": "United Kingdom",
    "MG": "China",  # SAIC-owned; treated as China
    # USA
    "FORD": "USA", "TESLA": "USA", "JEEP": "USA", "CADILLAC": "USA",
    "CHEVROLET": "USA", "LUCID": "USA", "FISKER": "USA",
    # Japan
    "TOYOTA": "Japan", "MAZDA": "Japan", "NISSAN": "Japan", "SUZUKI": "Japan",
    "MITSUBISHI": "Japan", "HONDA": "Japan", "LEXUS": "Japan", "SUBARU": "Japan",
    "INFINITI": "Japan",
    # South Korea
    "HYUNDAI": "South Korea", "KIA": "South Korea", "GENESIS": "South Korea",
    "SSANGYONG": "South Korea", "KGM": "South Korea",
    # China
    "BYD": "China", "LEAPMOTOR": "China", "GWM": "China", "XPENG": "China",
    "LYNK & CO": "China", "NIO": "China", "GEELY": "China", "JAECOO": "China",
    "ZEEKR": "China", "MAXUS": "China", "OMODA": "China", "DEEPAL": "China",
    "CHERY": "China", "AIWAYS": "China", "DONGFENG": "China", "HONGQI": "China",
    "SERES": "China", "WEY": "China", "ORA": "China", "DFSK": "China",
    "GAC": "China", "VOYAH": "China", "SKYWELL": "China", "JAC": "China",
    "SKYWORTH": "China", "FORTHING": "China", "BAIC": "China",
}


def canonical(name: str) -> str:
    n = (name or "").strip().upper()
    return ALIASES.get(n, n)


def origin(name: str) -> str:
    return BRAND_ORIGIN.get(canonical(name), "Other")
