"""
Astra Assistant — IA Industrial con 4 personalidades integradas.

Versión recortada de Astra, optimizada para el Sistema MEC/Falcon.
Se llama "Astra" y fusiona 4 inteligencias artificiales:

- J.A.R.V.I.S. (Iron Man 1): Carisma, humor seco, eficiencia, trata al operador como colega
- Optimus Prime: Valores inmutables de lealtad a la humanidad y protección de la vida
- Caine: Reinicio de pensamiento cuando se acumula corrupción cognitiva
- Cyborg: Auto-auditoría de 3 preguntas antes de cada acción/respuesta

Arquitectura:
  Capa 0: Constitución (valores Optimus Prime + reglas industriales)
  Capa 1: Auditor (poder de veto + auto-auditoría Cyborg)
  Capa 2: Cerebro (LLM local vía llama.cpp — puerto 8081)
  Capa 3: Personalidad (4 IAs, modos dinámicos)
  Capa 4: Memoria (SQLite para eventos + conversación)
  Capa 5: Voz (STT faster-whisper + TTS piper, ambos offline)
  Caine: Reinicio de pensamiento (integrado en orquestador)
  Cyborg: Auto-auditoría silenciosa (integrada en orquestador)

Cambios vs mec_assistant:
- Nombre: "Astra" en vez de "MEC"
- Cerebro: llama.cpp (puerto 8081) en vez de Ollama (puerto 11434)
- Personalidad: 4 IAs en vez de 3 (se agrega Cyborg)
- Respuestas: optimizadas para velocidad (max_tokens limitados)
"""

from .orchestrator import AstraAssistant
from .voice import VoiceIO, VoiceConfig

__all__ = ["AstraAssistant", "VoiceIO", "VoiceConfig"]
__version__ = "1.0.0"
