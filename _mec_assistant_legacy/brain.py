"""
Capa 2 — Cerebro cognitivo del asistente MEC.

Cliente para un servidor LLM local (Ollama) que permite al asistente MEC
entender preguntas del operador y generar respuestas inteligentes sobre
el estado del motor.

Simplificado respecto a Astra: solo modo local, sin cloud boost, sin modelo coder separado.
"""
from __future__ import annotations

from dataclasses import dataclass

# Modelos sugeridos por tier de hardware
MODEL_BY_TIER = {
    "ligera": "qwen2.5:3b-instruct",
    "recomendada": "qwen2.5:7b-instruct",
    "potente": "qwen2.5:14b-instruct",
}

Message = dict[str, str]


@dataclass
class BrainConfig:
    local_endpoint: str = "http://127.0.0.1:11434"
    local_model: str = "qwen2.5:3b-instruct"
    temperature: float = 0.3
    timeout_s: float = 60.0


class Brain:
    """Cerebro del asistente MEC — conexión a LLM local vía Ollama."""

    def __init__(self, config: BrainConfig, system_prompt: str) -> None:
        self.config = config
        self.system_prompt = system_prompt
        self._available: bool | None = None

    @classmethod
    def from_app_config(cls, cfg, system_prompt: str) -> "Brain":
        tier = cfg.hardware.tier
        auto = bool(cfg.get("brain", "auto_scale_by_hardware", default=True))
        bc = BrainConfig(
            local_endpoint=cfg.get("brain", "local_endpoint", default="http://127.0.0.1:11434"),
            local_model=(MODEL_BY_TIER.get(tier) if auto else cfg.get("brain", "local_model"))
            or "qwen2.5:3b-instruct",
            temperature=float(cfg.get("brain", "temperature", default=0.3)),
            timeout_s=float(cfg.get("brain", "timeout_s", default=60.0)),
        )
        return cls(bc, system_prompt)

    def is_available(self) -> bool:
        """Comprueba si hay un servidor Ollama local respondiendo."""
        try:
            import httpx
            r = httpx.get(f"{self.config.local_endpoint}/api/tags", timeout=2.0)
            self._available = r.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def chat(self, history: list[Message]) -> str:
        """
        Envía la conversación al modelo local y devuelve la respuesta.
        El system prompt se antepone automáticamente.
        """
        if not self.is_available():
            return (
                "[MEC] No encuentro mi cerebro local (Ollama). "
                "Verifica que esté corriendo en http://127.0.0.1:11434 "
                "y que el modelo esté descargado. "
                "Mientras tanto, el análisis basado en reglas sigue operativo."
            )

        messages: list[Message] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)

        try:
            import httpx
            payload = {
                "model": self.config.local_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": self.config.temperature},
            }
            r = httpx.post(
                f"{self.config.local_endpoint}/api/chat",
                json=payload,
                timeout=self.config.timeout_s,
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("message", {}) or {}).get("content", "").strip() or "(sin respuesta)"
        except Exception as exc:
            return f"[MEC] Error al procesar tu consulta: {exc}"

    def think(self, prompt: str) -> str:
        """Atajo de un solo turno (sin historial)."""
        return self.chat([{"role": "user", "content": prompt}])

    def analyze_motor_state(self, motor_data: dict) -> str:
        """
        Análisis contextual: genera un prompt con los datos actuales del motor
        y pide al LLM un diagnóstico técnico.
        """
        prompt = self._build_motor_context(motor_data)
        return self.think(prompt)

    def _build_motor_context(self, data: dict) -> str:
        """Construye un prompt técnico con el estado actual del motor."""
        return (
            "Analiza el estado actual del motor eléctrico con los siguientes datos en tiempo real:\n\n"
            f"  Tensión:            {data.get('v', 0):.1f} V\n"
            f"  Corriente:          {data.get('i', 0):.2f} A\n"
            f"  Potencia Activa:    {data.get('p', 0):.0f} W\n"
            f"  Potencia Reactiva:  {data.get('q', 0):.0f} VAr\n"
            f"  Potencia Aparente:  {data.get('s', 0):.0f} VA\n"
            f"  Factor de Potencia: {data.get('pf', 0):.3f}\n"
            f"  THD:                {data.get('thd', 0):.1f}%\n"
            f"  Vibración:          {data.get('vib', 0):.2f} mm/s\n"
            f"  Frecuencia:         {data.get('freq', 0):.1f} Hz\n"
            f"  Temperatura:        {data.get('temp', 0):.1f} °C\n"
            f"  Salud estimada:     {data.get('salud', 0)*100:.1f}%\n"
            f"\n"
            f"  Estado TensorFlow:  {data.get('tf_estado', 'N/A')}\n"
            f"  AE-Loss:            {data.get('ae_loss', 0):.5f}\n"
            f"  Salud LSTM:         {data.get('pred_salud', 0):.1f}%\n"
            f"  Anomalías acum.:    {data.get('n_anomalias', 0)}\n"
            "\nProporciona:\n"
            "1. Diagnóstico breve del estado actual\n"
            "2. Si hay algún parámetro fuera de norma, indica cuál y qué norma aplica\n"
            "3. Recomendación de acción (si aplica)\n"
            "Sé conciso (máximo 5 líneas)."
        )
