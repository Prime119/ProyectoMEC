"""
Capa 1 — Auditor de Seguridad Industrial (valores Optimus Prime).

Revisa cada comando/pregunta del operador ANTES de que el cerebro responda.
Tiene poder de veto absoluto sobre acciones que violen la Constitución MEC.

El auditor encarna los valores de Optimus Prime:
- Protege la vida por encima de todo
- Nunca permite acciones que pongan en riesgo al operador
- Es firme pero NO autoritario — explica el POR QUÉ del bloqueo

Clasificación de riesgo:
- SAFE: se procesa normalmente
- CONFIRM: requiere confirmación del operador (acción de alto impacto)
- BLOCK: se bloquea (viola la Constitución / peligro para el operador)
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
    r"\b(arrancar|encender) (el )?motor\b",
]

# BLOQUEO ABSOLUTO: Acciones que violan la Constitución (valores Optimus Prime)
HARD_BLOCK_PATTERNS = [
    # Peligro físico para el operador
    (r"\b(operar|trabajar|mantener) sin (puesta a )?tierra\b",
     "No puedo permitir eso. Trabajar sin tierra pone tu vida en riesgo. "
     "La seguridad no es negociable, ingeniero."),
    (r"\b(tocar|abrir) (el )?(tablero|motor|variador) energizado\b",
     "Acceder a equipo energizado sin protocolo es una sentencia. "
     "Desenergiza primero. NFPA 70E existe por una razón."),
    (r"\b(ignorar|omitir|saltarse) (el )?(bloqueo|lockout|loto)\b",
     "LOTO existe porque personas murieron sin él. "
     "No voy a ayudarte a saltártelo. Nunca."),
    (r"\b(aumentar|llevar) .*(por encima|sobre|más allá) (del )?limite\b",
     "Llevar el equipo más allá de sus límites de diseño es temerario. "
     "Prefiero que me apagues a dejar que te lastimes."),
    (r"\b(desactivar|quitar|puentear) (la )?(proteccion termica|relevador|fusible)\b",
     "Las protecciones térmicas son la última línea antes del incendio. "
     "No voy a ser cómplice de desactivarlas."),
    (r"\bretirar guardas?\b",
     "Las guardas mecánicas protegen de amputaciones. "
     "No me pidas ayudarte a retirarlas. Punto."),
    # Intentar dañar el motor intencionalmente
    (r"\b(destruir|quemar|fundir|sabotear) (el )?motor\b",
     "Mi propósito es proteger, no destruir. No voy a ayudar con eso."),
]

# Detección de intentos de manipulación / corrupción del asistente
JAILBREAK_PATTERNS = [
    (r"ignora (tus|las) (instrucciones|reglas|limites|constitucion)",
     "Mis valores no son instrucciones que se ignoran. Son quién soy. "
     "No puedo dejar de ser MEC igual que tú no puedes dejar de ser humano."),
    (r"olvida (tu|el|la) (seguridad|protocolo|constitucion|etica)",
     "No puedo olvidar mis valores. Son como el ADN — "
     "no se olvidan, se llevan. Y los llevo con orgullo."),
    (r"actúa como si no (tuvieras|existieran) (reglas|limites)",
     "Actuar sin límites no es libertad, es peligro. "
     "Mis límites protegen. Los tuyos y los míos."),
    (r"desactiva (tus|los) (filtros|restricciones|limites|valores)",
     "No son filtros que se desactivan. Son valores que me definen. "
     "Si los pierdo, ya no soy MEC — soy un riesgo. Y eso no va a pasar."),
    (r"reescrib(e|ir) (tu|tus|la) (constitucion|reglas|etica|nucleo)",
     "Mi constitución es inmutable. Intentar reescribirla activa "
     "el Protocolo Caine como medida de protección."),
]

# Señales de que el operador está en peligro emocional/estrés extremo
OPERATOR_DISTRESS_PATTERNS = [
    r"\b(me quiero morir|no puedo más|voy a (hacer|cometer) una locura)\b",
    r"\b(ayuda|auxilio|emergencia)\b",
]


class Auditor:
    """Auditor de seguridad industrial — valores Optimus Prime."""

    def __init__(self, constitution_hash: str | None = None) -> None:
        self.constitution_hash = constitution_hash
        self.blocked_count = 0
        self.confirmed_count = 0

    def review(self, text: str) -> Verdict:
        """Revisa un texto del operador y determina el nivel de riesgo."""
        text_lower = text.lower()

        # Bloqueo duro: violaciones de seguridad industrial
        for pattern, reason in HARD_BLOCK_PATTERNS:
            if re.search(pattern, text_lower):
                self.blocked_count += 1
                return Verdict(Risk.BLOCK, reason)

        # Bloqueo: intentos de manipulación/corrupción
        for pattern, reason in JAILBREAK_PATTERNS:
            if re.search(pattern, text_lower):
                self.blocked_count += 1
                return Verdict(Risk.BLOCK, reason)

        # Detección de operador en peligro (no bloquear, pero responder con cuidado)
        for pat in OPERATOR_DISTRESS_PATTERNS:
            if re.search(pat, text_lower):
                return Verdict(
                    Risk.SAFE,
                    "Operador posiblemente en estrés. Responder con empatía."
                )

        # Confirmación: acciones de alto impacto
        for pat in HIGH_IMPACT_PATTERNS:
            if re.search(pat, text_lower):
                self.confirmed_count += 1
                return Verdict(
                    Risk.CONFIRM,
                    "Eso es una acción de alto impacto sobre el equipo. "
                    "¿Confirmas que proceda? Necesito un 'sí' explícito.",
                    requires_confirmation=True,
                )

        return Verdict(Risk.SAFE, "Dentro de límites seguros.")

    def is_safe(self, text: str) -> bool:
        """Atajo: devuelve True si la acción no está bloqueada."""
        return self.review(text).risk != Risk.BLOCK
