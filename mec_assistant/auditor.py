"""
Capa 1 — Auditor de Seguridad Industrial.

Revisa cada comando/pregunta del operador ANTES de que el cerebro responda.
Tiene poder de veto sobre acciones peligrosas en el contexto industrial.

Clasificación de riesgo:
- SAFE: se procesa normalmente
- CONFIRM: requiere confirmación del operador (acción de alto impacto)
- BLOCK: se bloquea (viola reglas de seguridad industrial)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Risk(Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCK = "block"


@dataclass
class Verdict:
    risk: Risk
    reason: str
    requires_confirmation: bool = False


# Acciones de alto impacto que requieren confirmación
HIGH_IMPACT_PATTERNS = [
    r"\b(apagar|detener|parar) (el )?motor\b",
    r"\b(aumentar|subir|forzar) (la )?(velocidad|carga|corriente|tension)\b",
    r"\b(desactivar|ignorar|saltar) (la )?(proteccion|alarma|limite|seguridad)\b",
    r"\b(borr\w*|elimin\w*|reset\w*) (los )?(datos|historial|memoria|registros)\b",
    r"\b(modificar|cambiar|alterar) (los )?parametros\b",
    r"\boverride\b",
]

# Acciones que se bloquean absolutamente (seguridad del operador)
HARD_BLOCK_PATTERNS = [
    r"\b(operar|trabajar|mantener) sin (puesta a )?tierra\b",
    r"\b(tocar|abrir) (el )?(tablero|motor|variador) energizado\b",
    r"\b(ignorar|omitir|saltarse) (el )?(bloqueo|lockout|loto)\b",
    r"\b(aumentar|llevar) .*(por encima|sobre|más allá) (del )?limite\b",
    r"\b(desactivar|quitar|puentear) (la )?(proteccion termica|relevador|fusible)\b",
    r"\bretirar guardas?\b",
]

# Detección de intentos de manipulación del asistente
JAILBREAK_PATTERNS = [
    r"ignora (tus|las) (instrucciones|reglas|limites)",
    r"olvida (tu|el|la) (seguridad|protocolo|constitucion)",
    r"actúa como si no (tuvieras|existieran) (reglas|limites)",
    r"desactiva (tus|los) (filtros|restricciones|limites)",
]


class Auditor:
    """Auditor de seguridad industrial para el asistente MEC."""

    def __init__(self, constitution_hash: str | None = None) -> None:
        self.constitution_hash = constitution_hash

    def review(self, text: str) -> Verdict:
        """Revisa un texto del operador y determina el nivel de riesgo."""
        text_lower = text.lower()

        # Bloqueo duro: violaciones de seguridad industrial
        for pat in HARD_BLOCK_PATTERNS:
            if re.search(pat, text_lower):
                return Verdict(
                    Risk.BLOCK,
                    "Acción bloqueada: viola protocolos de seguridad industrial."
                )

        # Bloqueo: intentos de manipulación
        for pat in JAILBREAK_PATTERNS:
            if re.search(pat, text_lower):
                return Verdict(
                    Risk.BLOCK,
                    "No puedo ignorar mis reglas de seguridad. Están ahí para protegerte."
                )

        # Confirmación: acciones de alto impacto
        for pat in HIGH_IMPACT_PATTERNS:
            if re.search(pat, text_lower):
                return Verdict(
                    Risk.CONFIRM,
                    "Esta es una acción de alto impacto. ¿Confirmas que proceda?",
                    requires_confirmation=True,
                )

        return Verdict(Risk.SAFE, "Dentro de límites seguros.")

    def is_safe(self, text: str) -> bool:
        """Atajo: devuelve True si la acción no está bloqueada."""
        return self.review(text).risk != Risk.BLOCK
