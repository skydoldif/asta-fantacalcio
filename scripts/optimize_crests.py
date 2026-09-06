"""Ripulisce e alleggerisce gli SVG degli stemmi in ``static/loghi/``.

Gli stemmi scaricati da internet arrivano con metadati, commenti e coordinate
a otto decimali: roba che il browser scarica e butta via. Lo stemma si vede a
28 px, quindi due decimali sono gia' molto piu' di quanto l'occhio distingua.

Aggiunge anche il ``viewBox`` quando manca: senza, l'SVG non si ridimensiona
e nella pagina esce con la sua dimensione nativa.

Uso::

    python scripts/optimize_crests.py                 # riscrive i file
    python scripts/optimize_crests.py --dry-run       # mostra solo il bilancio
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from xml.etree import ElementTree as ET

CRESTS_DIR = Path(__file__).resolve().parents[1] / "static" / "loghi"

#: Blocchi che non servono a disegnare nulla.
_INUTILI = re.compile(
    r"<!--.*?-->|<metadata\b.*?</metadata>|<title\b.*?</title>|<desc\b.*?</desc>",
    re.S | re.I,
)
_TRA_TAG = re.compile(r">\s+<")
_ATTRIBUTI_GEOMETRICI = re.compile(r'\b(d|points)="([^"]*)"')
_DECIMALI = re.compile(r"-?\d+\.\d+")


def _arrotonda(testo: str, decimali: int) -> str:
    """Riduce i decimali dei numeri dentro un attributo geometrico."""

    def sostituisci(match: re.Match[str]) -> str:
        valore = f"{round(float(match.group()), decimali):.{decimali}f}"
        ripulito = valore.rstrip("0").rstrip(".")
        return ripulito if ripulito not in ("", "-") else "0"

    return _DECIMALI.sub(sostituisci, testo)


def _assicura_viewbox(svg: str) -> str:
    """Aggiunge ``viewBox`` ricavandolo da ``width``/``height``, se manca."""
    if "viewBox" in svg:
        return svg
    larghezza = re.search(r'<svg[^>]*\bwidth="([\d.]+)', svg)
    altezza = re.search(r'<svg[^>]*\bheight="([\d.]+)', svg)
    if not (larghezza and altezza):
        return svg
    box = f'viewBox="0 0 {larghezza.group(1)} {altezza.group(1)}"'
    return svg.replace("<svg", f"<svg {box}", 1)


def ottimizza(svg: str, decimali: int = 2) -> str:
    """Restituisce l'SVG ripulito.

    Raises:
        ValueError: se il risultato non e' XML valido.
    """
    ripulito = _INUTILI.sub("", svg)
    ripulito = _ATTRIBUTI_GEOMETRICI.sub(
        lambda m: f'{m.group(1)}="{_arrotonda(m.group(2), decimali)}"', ripulito
    )
    ripulito = _TRA_TAG.sub("><", ripulito).strip()
    ripulito = _assicura_viewbox(ripulito)
    try:
        ET.fromstring(ripulito)
    except ET.ParseError as exc:
        raise ValueError(f"l'ottimizzazione ha prodotto XML non valido: {exc}") from exc
    return ripulito


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--decimals", type=int, default=2)
    args = parser.parse_args()

    prima_totale = dopo_totale = 0
    for percorso in sorted(CRESTS_DIR.glob("*.svg")):
        originale = percorso.read_text(encoding="utf-8")
        nuovo = ottimizza(originale, args.decimals)
        prima, dopo = len(originale.encode()), len(nuovo.encode())
        prima_totale += prima
        dopo_totale += dopo
        risparmio = 100 - dopo * 100 / prima if prima else 0
        nota = " +viewBox" if "viewBox" not in originale else ""
        print(f"{percorso.name:<16} {prima:>7,} -> {dopo:>7,}  (-{risparmio:4.1f}%){nota}")
        if not args.dry_run:
            percorso.write_text(nuovo, encoding="utf-8")

    print(
        f"\ntotale {prima_totale:,} -> {dopo_totale:,} byte "
        f"(-{100 - dopo_totale * 100 / prima_totale:.1f}%)"
    )
    if args.dry_run:
        print("(--dry-run: nessun file scritto)")


if __name__ == "__main__":
    main()
