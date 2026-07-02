"""
Orquestador — une todas las capas del asistente MEC.

Pipeline (inspirado en Astra/F.R.I.D.A.Y.):
  entrada del operador -> auditor revisa -> cerebro propone -> memoria registra

Además, puede recibir datos del motor en tiempo real para dar respuestas
contextualizadas sobre el estado del equipo.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .auditor import Auditor, Risk
from .brain import Brain
from .config import MECConfig, load_config
from .constitution import Constitution, load_constitution
from .memory import Memory
from .personality import Personality


MAX_HISTORY_TURNS = 10  # Límite de memoria de trabajo (conversación activa)


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

        return cls(
            config=config,
            constitution=constitution,
            personality=personality,
            auditor=auditor,
            memory=memory,
            brain=brain,
        )

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
        Procesa una entrada del operador pasando por el auditor.
        Retorna la respuesta del asistente.
        """
        # 1. Auditor revisa la entrada
        verdict = self.auditor.review(user_text)
        if verdict.risk == Risk.BLOCK:
            self.memory.log_event("seguridad", f"Bloqueado: {user_text}", severity="warning")
            return f"🚫 {verdict.reason}"
        if verdict.risk == Risk.CONFIRM:
            self.memory.remember("accion_pendiente", user_text)
            return f"⚠️ {verdict.reason}"

        # 2. Inyectar contexto del motor si aplica
        context_msg = self._build_context_injection()

        # 3. Agregar al historial y enviar al cerebro
        with self._lock:
            if context_msg:
                # Insertar el contexto como mensaje del sistema justo antes del turno
                self.history.append({"role": "system", "content": context_msg})
            self.history.append({"role": "user", "content": user_text})
            response = self.brain.chat(self.history)
            self.history.append({"role": "assistant", "content": response})
            self._trim_history()

        # 4. Registrar en memoria
        self.memory.log_conversation("user", user_text)
        self.memory.log_conversation("assistant", response)

        return response

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
            return "[MEC] No tengo datos del motor todavía. Espera a que la telemetría se estabilice."
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
        return (
            "[CONTEXTO DEL MOTOR EN TIEMPO REAL]\n"
            f"V={data.get('v', 0):.1f}V | I={data.get('i', 0):.2f}A | "
            f"P={data.get('p', 0):.0f}W | PF={data.get('pf', 0):.3f} | "
            f"THD={data.get('thd', 0):.1f}% | Vib={data.get('vib', 0):.2f}mm/s | "
            f"Temp={data.get('temp', 0):.1f}°C | Salud={data.get('salud', 0)*100:.1f}% | "
            f"TF-Estado={data.get('tf_estado', 'N/A')}"
        )

    def _trim_history(self) -> None:
        """Mantiene el historial dentro del límite."""
        max_msgs = MAX_HISTORY_TURNS * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]


def _build_system_prompt(constitution: Constitution, personality: Personality) -> str:
    return (
        "### REGLAS DE SEGURIDAD INDUSTRIAL (inviolables)\n"
        f"{constitution.text}\n\n"
        "### PERSONALIDAD E INSTRUCCIONES\n"
        f"{personality.system_prompt_fragment()}\n"
    )
