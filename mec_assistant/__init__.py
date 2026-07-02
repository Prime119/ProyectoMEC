"""
MEC Assistant — Asistente cognitivo industrial integrado.

Versión simplificada (1/3) del proyecto Astra, adaptada al dominio de monitoreo
de motores eléctricos industriales. Se llama "MEC" y está especializado en:
- Análisis inteligente de telemetría de motores
- Recomendaciones de mantenimiento predictivo
- Conversación técnica con el operador/ingeniero
- Seguridad industrial (nunca recomienda acciones peligrosas)

Arquitectura (simplificada de Astra):
  Capa 0: Constitución industrial (reglas de seguridad inmutables)
  Capa 1: Auditor (revisa comandos antes de ejecutar)
  Capa 2: Cerebro (LLM local vía Ollama)
  Capa 3: Personalidad (tono técnico, profesional, proactivo)
  Capa 4: Memoria (SQLite para historial de eventos)
"""

from .orchestrator import MECAssistant

__all__ = ["MECAssistant"]
__version__ = "0.1.0"
