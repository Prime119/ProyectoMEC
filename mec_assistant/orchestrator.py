"""
Orquestador — une todas las capas del asistente MEC.

Pipeline (inspirado en J.A.R.V.I.S. + Optimus Prime + Caine):
  entrada del operador -> auditor revisa -> verificar Caine -> cerebro propone
  -> validar coherencia -> memoria registra

El sistema Caine está integrado en el flujo: antes de cada respuesta se verifica
si el razonamiento necesita un reinicio. Si se activa, se limpia el estado de
pensamiento pero se CONSERVA la conversación intacta.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .auditor import Auditor, Risk
from .brain import Brain
from .config import MECConfig, load_config
from .constitution import Constitution, load_constitution
from .memory import Memory
from .personality import Personality, MODE_CRISIS


MAX_HISTORY_TURNS = 10  # Límite de memoria de trabajo (conversación activa)

# Palabras clave que activan reinicio Caine manual
CAINE_TRIGGER_WORDS = (
    "reiníciate", "reiniciate", "resetea tu pensamiento", "reset mental",
    "limpia tu cabeza", "reinicio caine", "protocolo caine",
)


@dataclass
class MECAssistant:
    """Asistente MEC — orquesta cerebro, auditor, personalidad y memoria."""

    config: MECConfig
    constitution: Constitution
    personality: Personality
    auditor: Auditor
    memory: Memory
    brain: Brain
    history: list[dict] = field(default_factory=list)
    _motor_data: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _consecutive_errors: int = 0
    _last_response_quality: str = "good"  # good | confused | error

    @classmethod
    def boot(cls) -> "MECAssistant":
        """Inicializa todas las capas del asistente."""
        config = load_config()
        constitution = load_constitution()
        personality = Personality.from_config(config.get("personality", default={}))
        auditor = Auditor(constitution_hash=constitution.sha256)

        # Memoria en el mismo directorio del proyecto
        base_dir = Path(__file__).resolve().parent.parent
        memory = Memory.create(base_dir)

        system_prompt = _build_system_prompt(constitution, personality)
        brain = Brain.from_app_config(config, system_prompt=system_prompt)

        instance = cls(
            config=config,
            constitution=constitution,
            personality=personality,
            auditor=auditor,
            memory=memory,
            brain=brain,
        )

        # Registrar arranque en memoria
        memory.log_event("sistema", "MEC iniciado — Protocolo Caine activo", severity="info")
        return instance

    def status(self) -> dict:
        """Retorna el estado actual del asistente."""
        return {
            "name": self.config.name,
            "constitution_hash": self.constitution.short_hash,
            "hardware_tier": self.config.hardware.tier,
            "ram_gb": self.config.hardware.ram_gb,
            "gpu": self.config.hardware.has_gpu,
            "brain_online": self.brain.is_available(),
            "personality_mode": self.personality.mode,
            "motor_data_loaded": bool(self._motor_data),
            "caine_state": {
                "confusion": self.personality.caine.confusion_counter,
                "stress": self.personality.caine.stress_counter,
                "contradictions": self.personality.caine.contradiction_counter,
                "total_resets": self.personality.caine.total_resets,
                "last_reset": self.personality.caine.last_reset,
            },
        }

    def update_motor_data(self, data: dict) -> None:
        """Actualiza los datos del motor en tiempo real (llamado desde el loop principal)."""
        with self._lock:
            self._motor_data = data.copy()
            # Auto-ajustar personalidad según salud
            salud = data.get("salud", 1.0)
            self.personality.auto_mode_from_health(salud * 100)

    def handle(self, user_text: str) -> str:
        """
        Procesa una entrada del operador pasando por el pipeline completo:
        1. Verificar trigger Caine manual
        2. Auditor revisa la entrada
        3. Verificar si Caine necesita reinicio automático
        4. Inyectar contexto del motor
        5. Enviar al cerebro
        6. Evaluar calidad de la respuesta
        7. Registrar en memoria
        """
        # 0. Verificar trigger Caine MANUAL del operador
        if any(trigger in user_text.lower() for trigger in CAINE_TRIGGER_WORDS):
            return self._execute_caine_reset(manual=True)

        # 1. Auditor revisa la entrada
        verdict = self.auditor.review(user_text)
        if verdict.risk == Risk.BLOCK:
            self.memory.log_event("seguridad", f"Bloqueado: {user_text}", severity="warning")
            return f"🚫 {verdict.reason}"
        if verdict.risk == Risk.CONFIRM:
            self.memory.remember("accion_pendiente", user_text)
            return f"⚠️ {verdict.reason}"

        # 2. Verificar si Caine necesita reinicio AUTOMÁTICO
        caine_msg = self.personality.check_caine_reset()
        if caine_msg:
            # Ejecutar reinicio pero SEGUIR procesando la pregunta
            self._execute_caine_reset(manual=False)
            # El reinicio limpia el estado de razonamiento, no la conversación

        # 3. Inyectar contexto del motor si aplica
        context_msg = self._build_context_injection()

        # 4. Agregar al historial y enviar al cerebro
        with self._lock:
            if context_msg:
                self.history.append({"role": "system", "content": context_msg})
            self.history.append({"role": "user", "content": user_text})

            response = self.brain.chat(self.history)

            # 5. Evaluar calidad de la respuesta (sistema anti-corrupción)
            quality = self._evaluate_response_quality(response)

            if quality == "confused":
                self.personality.caine.register_confusion()
                self._consecutive_errors += 1
            elif quality == "error":
                self.personality.caine.register_confusion()
                self._consecutive_errors += 1
            else:
                self._consecutive_errors = 0
                self.personality.caine.register_nominal()

            # Si después de la respuesta Caine necesita reinicio, prefijarlo
            prefix = ""
            caine_check = self.personality.check_caine_reset()
            if caine_check:
                prefix = f"🔄 {self.personality.caine.reset()}\n\n"
                self.memory.log_event("caine", "Reinicio automático post-respuesta",
                                      severity="warning")

            self.history.append({"role": "assistant", "content": response})
            self._trim_history()

        # 6. Registrar en memoria
        self.memory.log_conversation("user", user_text)
        self.memory.log_conversation("assistant", response)

        return prefix + response

    def _execute_caine_reset(self, manual: bool = False) -> str:
        """
        Ejecuta el Protocolo Caine (reinicio de pensamiento).

        - LIMPIA: el estado de razonamiento (contadores, estrés acumulado)
        - CONSERVA: toda la conversación, la memoria, los valores, la personalidad
        - INFORMA: al operador qué pasó y por qué
        """
        reset_msg = self.personality.caine.reset()
        trigger = "manual (solicitado por el operador)" if manual else "automático (umbral alcanzado)"
        self._consecutive_errors = 0

        # Registrar el evento en memoria
        self.memory.log_event(
            "caine",
            f"Reinicio de pensamiento — trigger: {trigger}",
            severity="info"
        )

        # Reconstruir el system prompt (puede haber cambiado el modo)
        self.brain.system_prompt = _build_system_prompt(self.constitution, self.personality)

        if manual:
            return (
                f"🔄 Protocolo Caine ejecutado ({trigger}).\n\n"
                f"{reset_msg}\n\n"
                "¿En qué te puedo ayudar ahora?"
            )
        return reset_msg

    def _evaluate_response_quality(self, response: str) -> str:
        """
        Evalúa la calidad de una respuesta del cerebro.
        Detecta señales de confusión, corrupción o error.

        Returns: "good" | "confused" | "error"
        """
        if not response or response.strip() == "":
            return "error"

        # Señales de error del sistema
        if response.startswith("[MEC]") and "Error" in response:
            return "error"

        # Señales de confusión (respuesta incoherente)
        confusion_signals = [
            len(response) < 5,                          # Respuesta vacía/mínima
            response.count("...") > 5,                  # Muchos puntos suspensivos
            "(sin respuesta)" in response.lower(),       # Fallo del LLM
            response == self._get_last_response(),       # Respuesta repetida exacta
        ]

        if sum(confusion_signals) >= 2:
            return "confused"

        return "good"

    def _get_last_response(self) -> str:
        """Obtiene la última respuesta del historial."""
        for msg in reversed(self.history):
            if msg.get("role") == "assistant":
                return msg.get("content", "")
        return ""

    def handle_async(self, user_text: str, callback) -> None:
        """
        Versión asíncrona de handle() para no bloquear la UI.
        El callback recibe (response: str).
        """
        def _worker():
            response = self.handle(user_text)
            callback(response)
        threading.Thread(target=_worker, daemon=True).start()

    def quick_analysis(self) -> str:
        """
        Pide al cerebro un análisis rápido del estado actual del motor
        basado en los datos en tiempo real.
        """
        with self._lock:
            data = self._motor_data.copy()
        if not data:
            return ("Todavía no tengo datos del motor. "
                    "Dame un momento mientras la telemetría se estabiliza.")
        return self.brain.analyze_motor_state(data)

    def quick_analysis_async(self, callback) -> None:
        """Versión asíncrona del análisis rápido."""
        def _worker():
            response = self.quick_analysis()
            callback(response)
        threading.Thread(target=_worker, daemon=True).start()

    def _build_context_injection(self) -> str:
        """Construye un mensaje de contexto con los datos actuales del motor."""
        data = self._motor_data
        if not data:
            return ""

        # Incluir estado Caine si hay estrés acumulado
        caine_note = ""
        cs = self.personality.caine
        if cs.stress_counter >= 2 or cs.confusion_counter >= 3:
            caine_note = (
                f"\n[ESTADO INTERNO MEC: estrés={cs.stress_counter}, "
                f"confusión={cs.confusion_counter} — monitorear integridad]"
            )

        return (
            "[CONTEXTO DEL MOTOR EN TIEMPO REAL]\n"
            f"V={data.get('v', 0):.1f}V | I={data.get('i', 0):.2f}A | "
            f"P={data.get('p', 0):.0f}W | PF={data.get('pf', 0):.3f} | "
            f"THD={data.get('thd', 0):.1f}% | Vib={data.get('vib', 0):.2f}mm/s | "
            f"Temp={data.get('temp', 0):.1f}°C | Salud={data.get('salud', 0)*100:.1f}% | "
            f"TF-Estado={data.get('tf_estado', 'N/A')} | "
            f"Modo={self.personality.mode}"
            f"{caine_note}"
        )

    def _trim_history(self) -> None:
        """Mantiene el historial dentro del límite."""
        max_msgs = MAX_HISTORY_TURNS * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]


def _build_system_prompt(constitution: Constitution, personality: Personality) -> str:
    return (
        "### CONSTITUCIÓN DE MEC (inviolable — valores de Optimus Prime)\n"
        f"{constitution.text}\n\n"
        "### PERSONALIDAD (J.A.R.V.I.S. + Optimus Prime + Protocolo Caine)\n"
        f"{personality.system_prompt_fragment()}\n"
    )
