"""
Capa 0 — Núcleo de Seguridad Industrial Inmutable.

Carga las reglas de seguridad industrial (ethics_industrial.md) en SOLO LECTURA
y calcula un hash de integridad. Inspirado en el núcleo ético de Astra pero
especializado para el dominio de motores eléctricos industriales.
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
    """Verifica que las reglas de seguridad no hayan sido alteradas."""
    try:
        current = load_constitution()
    except Exception:
        return False
    if expected_hash is None:
        return True
    return current.sha256 == expected_hash


_FALLBACK_RULES = """
# Reglas de Seguridad Industrial — MEC Assistant

1. NUNCA recomendar acciones que pongan en riesgo la integridad física del operador.
2. NUNCA sugerir omitir procedimientos de seguridad o normativas (NOM, IEEE, IEC).
3. Ante una anomalía crítica, SIEMPRE priorizar la recomendación de PARO seguro.
4. No ejecutar acciones de alto impacto sin confirmación del operador.
5. Ser transparente sobre las limitaciones del análisis predictivo.
"""
