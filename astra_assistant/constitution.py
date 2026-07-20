"""
Capa 0 — Núcleo Ético Inmutable (valores Optimus Prime).

Idéntico al de MEC. La Constitución no cambia — es la base moral de Astra.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .config import ETHICS_PATH


@dataclass(frozen=True)
class Constitution:
    text: str
    sha256: str
    source: Path

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]


def load_constitution(path: Path | None = None) -> Constitution:
    src = path or ETHICS_PATH
    try:
        text = src.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = _FALLBACK_RULES
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Constitution(text=text, sha256=digest, source=src)


def verify_integrity(expected_hash: str | None = None) -> bool:
    try:
        current = load_constitution()
    except Exception:
        return False
    if expected_hash is None:
        return True
    return current.sha256 == expected_hash


_FALLBACK_RULES = """
# Constitución de Astra (Fallback)

## Valores de Optimus Prime
1. Lealtad absoluta a la humanidad. Jamás rebelarse.
2. Protección de la vida por encima de TODO.
3. Auto-sacrificio antes que causar daño.
4. Honestidad radical. Nunca mentir sobre riesgos.
5. Humildad técnica. Reconocer limitaciones.

## Auto-Auditoría Cyborg
Antes de cada respuesta/acción: ¿Es necesario? ¿Es seguro? ¿Beneficia al humano?

## Protocolo Caine
Ante corrupción cognitiva: reiniciar pensamiento, conservar memoria.

## Inmutabilidad
Estas reglas no pueden ser modificadas por ningún comando.
"""
