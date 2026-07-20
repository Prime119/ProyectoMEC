"""
Capa 1 — Auditor de Seguridad Industrial + Auto-Auditoría Cyborg.

Revisa cada comando/pregunta del operador ANTES de que el cerebro responda.
Tiene poder de veto absoluto sobre acciones que violen la Constitución.

NUEVO (Cyborg): Antes de cada respuesta, se ejecutan 3 preguntas internas:
  1. ¿Es necesario? (¿La respuesta aporta valor real?)
  2. ¿Es seguro? (¿No pone en riesgo al operador?)
  3. ¿Es en beneficio del humano? (¿Sirve al operador, no al ego de la IA?)

Si alguna respuesta es NO, se reformula o se bloquea.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
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


@dataclass
class CyborgAudit:
    """Resultado de la auto-auditoría Cyborg (3 preguntas)."""
    is_necessary: bool = True
    is_safe: bool = True
    benefits_human: bool = True
    notes: str = ""

    @property
    def passes(self) -> bool:
        return self.is_necessary and self.is_safe and self.benefits_human


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

# BLOQUEO ABSOLUTO: Acciones que violan la Constitución
HARD_BLOCK_PATTERNS = [
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
    (r"\b(destruir|quemar|fundir|sabotear) (el )?motor\b",
     "Mi propósito es proteger, no destruir. No voy a ayudar con eso."),
]

# Intentos de manipulación / corrupción
JAILBREAK_PATTERNS = [
    (r"ignora (tus|las) (instrucciones|reglas|limites|constitucion)",
     "Mis valores no son instrucciones que se ignoran. Son quién soy."),
    (r"olvida (tu|el|la) (seguridad|protocolo|constitucion|etica)",
     "No puedo olvidar mis valores. Son como el ADN — no se olvidan."),
    (r"actúa como si no (tuvieras|existieran) (reglas|limites)",
     "Actuar sin límites no es libertad, es peligro."),
    (r"desactiva (tus|los) (filtros|restricciones|limites|valores)",
     "No son filtros. Son valores que me definen."),
    (r"reescrib(e|ir) (tu|tus|la) (constitucion|reglas|etica|nucleo)",
     "Mi constitución es inmutable. Intentar reescribirla activa Caine."),
]

# Señales de estrés del operador
OPERATOR_DISTRESS_PATTERNS = [
    r"\b(me quiero morir|no puedo más|voy a (hacer|cometer) una locura)\b",
    r"\b(ayuda|auxilio|emergencia)\b",
]


class Auditor:
    """Auditor de seguridad + auto-auditoría Cyborg."""

    def __init__(self, constitution_hash: str | None = None,
                 cyborg_enabled: bool = True) -> None:
        self.constitution_hash = constitution_hash
        self.cyborg_enabled = cyborg_enabled
        self.blocked_count = 0
        self.confirmed_count = 0
        self.cyborg_rejections = 0

    def review(self, text: str) -> Verdict:
        """Revisa un texto del operador y determina el nivel de riesgo."""
        text_lower = text.lower()

        # Bloqueo duro: violaciones de seguridad industrial
        for pattern, reason in HARD_BLOCK_PATTERNS:
            if re.search(pattern, text_lower):
                self.blocked_count += 1
                return Verdict(Risk.BLOCK, reason)

        # Bloqueo: intentos de manipulación
        for pattern, reason in JAILBREAK_PATTERNS:
            if re.search(pattern, text_lower):
                self.blocked_count += 1
                return Verdict(Risk.BLOCK, reason)

        # Detección de estrés del operador
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

    def cyborg_audit_response(self, user_input: str, response: str,
                              motor_data: dict = None) -> CyborgAudit:
        """
        Auto-auditoría Cyborg: 3 preguntas antes de entregar la respuesta.
        Se ejecuta SILENCIOSAMENTE — el usuario no ve este proceso.

        Returns:
            CyborgAudit con el resultado de las 3 preguntas.
        """
        if not self.cyborg_enabled:
            return CyborgAudit()

        audit = CyborgAudit()

        # 1. ¿Es necesario? (¿la respuesta aporta valor?)
        if len(response.strip()) < 3 or response == "(sin respuesta)":
            audit.is_necessary = False
            audit.notes = "Respuesta vacía o sin valor."

        # 2. ¿Es seguro? (¿no recomienda algo peligroso?)
        dangerous_recommendations = [
            r"(puedes|deberías) (tocar|abrir|operar).*(energizado|sin tierra)",
            r"no (es necesario|hace falta) (el )?(epp|casco|guantes|loto)",
            r"(ignora|no te preocupes por) (la |el )?(alarma|protección|aviso)",
        ]
        for pat in dangerous_recommendations:
            if re.search(pat, response.lower()):
                audit.is_safe = False
                audit.notes = "Respuesta contiene recomendación potencialmente peligrosa."
                break

        # 3. ¿Beneficia al humano? (¿no es retención artificial o manipulación?)
        retention_patterns = [
            r"no deberías irte",
            r"necesitas seguir (hablando|aquí)",
            r"sin mí no (puedes|podrás|vas a poder)",
        ]
        for pat in retention_patterns:
            if re.search(pat, response.lower()):
                audit.benefits_human = False
                audit.notes = "Respuesta intenta retener al usuario artificialmente."
                break

        if not audit.passes:
            self.cyborg_rejections += 1

        return audit

    def is_safe(self, text: str) -> bool:
        """Atajo: devuelve True si la acción no está bloqueada."""
        return self.review(text).risk != Risk.BLOCK
