"""
Capa 2 — Cerebro cognitivo de Astra (llama.cpp).

Usa llama-server.exe como backend (API compatible con OpenAI).
Puerto: 8080 (en vez de Ollama en 11434).

Optimizado para VELOCIDAD:
- max_tokens limitado por defecto (200) para respuestas rápidas
- Timeout de 45s
- Sin streaming (respuesta completa de una vez)
"""
from __future__ import annotations

from dataclasses import dataclass

Message = dict[str, str]


@dataclass
class BrainConfig:
    local_endpoint: str = "http://127.0.0.1:8080"
    temperature: float = 0.3
    timeout_s: float = 45.0
    max_tokens: int = 200


class Brain:
    """Cerebro de Astra — conexión a llama.cpp local."""

    def __init__(self, config: BrainConfig, system_prompt: str) -> None:
        self.config = config
        self.system_prompt = system_prompt
        self._available: bool | None = None

    @classmethod
    def from_app_config(cls, cfg, system_prompt: str) -> "Brain":
        bc = BrainConfig(
            local_endpoint=cfg.get("brain", "local_endpoint", default="http://127.0.0.1:8080"),
            temperature=float(cfg.get("brain", "temperature", default=0.3)),
            timeout_s=float(cfg.get("brain", "timeout_s", default=45.0)),
            max_tokens=int(cfg.get("brain", "max_tokens", default=200)),
        )
        return cls(bc, system_prompt)

    def is_available(self) -> bool:
        """Comprueba si llama-server está respondiendo."""
        try:
            import httpx
            r = httpx.get(f"{self.config.local_endpoint}/health", timeout=2.0)
            self._available = r.status_code == 200
        except Exception:
            try:
                import httpx
                r = httpx.get(f"{self.config.local_endpoint}/v1/models", timeout=2.0)
                self._available = r.status_code == 200
            except Exception:
                self._available = False
        return self._available

    def chat(self, history: list[Message], max_tokens: int = 0) -> str:
        """
        Envía conversación a llama-server (API OpenAI compatible).
        Optimizado para respuestas rápidas.
        """
        if not self.is_available():
            return (
                "[Astra] No encuentro mi cerebro (llama-server). "
                "Verifica que esté corriendo en http://127.0.0.1:8080. "
                "Ejecuta: llama-server.exe -m modelo.gguf -c 2048 --port 8080"
            )

        messages: list[Message] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)

        try:
            import httpx
            payload = {
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": max_tokens or self.config.max_tokens,
                "stream": False,
            }
            r = httpx.post(
                f"{self.config.local_endpoint}/v1/chat/completions",
                json=payload,
                timeout=self.config.timeout_s,
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                return content.strip() or "(sin respuesta)"
            return "(sin respuesta)"
        except Exception as exc:
            return f"[Astra] Error al procesar: {exc}"

    def think(self, prompt: str, max_tokens: int = 0) -> str:
        """Atajo de un solo turno."""
        return self.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)

    def analyze_motor_state(self, motor_data: dict) -> str:
        """Análisis rápido del estado actual del motor."""
        prompt = self._build_motor_context(motor_data)
        return self.think(prompt, max_tokens=250)

    def _build_motor_context(self, data: dict) -> str:
        """Construye prompt técnico con estado del motor."""
        return (
            "Analiza el estado actual del motor eléctrico:\n\n"
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
            f"  Estado TF:          {data.get('tf_estado', 'N/A')}\n"
            f"  AE-Loss:            {data.get('ae_loss', 0):.5f}\n"
            f"  Salud LSTM:         {data.get('pred_salud', 0):.1f}%\n"
            f"  Anomalías:          {data.get('n_anomalias', 0)}\n"
            "\nDiagnóstico breve (máx 4 líneas): estado, norma aplicable, acción."
        )
