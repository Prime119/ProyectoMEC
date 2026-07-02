"""
MEC Assistant — Asistente cognitivo industrial con personalidad JARVIS.

Versión simplificada (1/3) del proyecto Astra, adaptada al dominio de monitoreo
de motores eléctricos industriales. Se llama "MEC" y combina:

- J.A.R.V.I.S. (Iron Man 1): Carisma, humor seco, eficiencia, trata al operador como colega
- Optimus Prime: Valores inmutables de lealtad a la humanidad y protección de la vida
- Caine: Reinicio de pensamiento cuando se acumula corrupción cognitiva

Arquitectura:
  Capa 0: Constitución (valores Optimus Prime + reglas industriales)
  Capa 1: Auditor (poder de veto con explicaciones humanas)
  Capa 2: Cerebro (LLM local vía Ollama)
  Capa 3: Personalidad (JARVIS ingeniero, modos dinámicos)
  Capa 4: Memoria (SQLite para eventos + conversación)
  Capa 5: Voz (STT faster-whisper + TTS piper, ambos offline)
  Caine: Reinicio de pensamiento (integrado en orquestador)
"""

from .orchestrator import MECAssistant
from .voice import VoiceIO, VoiceConfig

__all__ = ["MECAssistant", "VoiceIO", "VoiceConfig"]
__version__ = "0.2.0"
