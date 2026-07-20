"""
Orquestador — une todas las capas de Astra.

Pipeline (JARVIS + Optimus + Caine + Cyborg):
  entrada → auditor → Caine check → cerebro → Cyborg audit → memoria

Optimizado para VELOCIDAD: max_tokens limitado, sin overhead.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from .auditor import Auditor, Risk
from .brain import Brain
from .config import AstraConfig, load_config
from .constitution import Constitution, load_constitution
from .memory import Memory
from .personality import Personality, MODE_CRISIS


MAX_HISTORY_TURNS = 8

CAINE_TRIGGER_WORDS = (
    "reiníciate", "reiniciate", "resetea tu pensamiento",
    "reset mental", "limpia tu cabeza", "protocolo caine",
)



def _build_system_prompt(constitution: Constitution, personality: Personality) -> str:
    """Construye el system prompt completo."""
    parts = [personality.system_prompt_fragment()]
    # Agregar reglas éticas resumidas (no el doc completo para ahorrar tokens)
    parts.append(
        "\nVALORES INMUTABLES: Nunca mientes sobre riesgos. "
        "Nunca recomiendas saltarse LOTO/EPP. "
        "La vida del operador está por encima del motor."
    )
    return "\n".join(parts)


@dataclass
class AstraAssistant:
    """Asistente Astra — orquesta cerebro, auditor, personalidad y memoria."""

    config: AstraConfig
    constitution: Constitution
    personality: Personality
    auditor: Auditor
    memory: Memory
    brain: Brain
    history: list[dict] = field(default_factory=list)
    _motor_data: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _consecutive_errors: int = 0

    @classmethod
    def boot(cls) -> "AstraAssistant":
        """Inicializa todas las capas."""
        config = load_config()
        constitution = load_constitution()
        personality = Personality.from_config(
            config.get("personality", default={})
        )
        auditor = Auditor(
            constitution_hash=constitution.sha256,
            cyborg_enabled=personality.cyborg_enabled,
        )

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
        memory.log_event("sistema", "Astra iniciada — 4 IAs activas", severity="info")
        return instance



    def status(self) -> dict:
        return {
            "name": self.config.name,
            "constitution_hash": self.constitution.short_hash,
            "hardware_tier": self.config.hardware.tier,
            "ram_gb": self.config.hardware.ram_gb,
            "brain_online": self.brain.is_available(),
            "personality_mode": self.personality.mode,
            "motor_data_loaded": bool(self._motor_data),
            "caine_state": {
                "confusion": self.personality.caine.confusion_counter,
                "stress": self.personality.caine.stress_counter,
                "total_resets": self.personality.caine.total_resets,
            },
            "cyborg_rejections": self.auditor.cyborg_rejections,
        }

    def update_motor_data(self, data: dict) -> None:
        """Actualiza datos del motor en tiempo real."""
        with self._lock:
            self._motor_data = data.copy()
            salud = data.get("salud", 1.0)
            self.personality.auto_mode_from_health(salud * 100)

    def handle(self, user_text: str) -> str:
        """
        Pipeline completo:
        1. Trigger Caine manual
        2. Auditor revisa entrada
        3. Caine check automático
        4. Contexto del motor
        5. Cerebro responde
        6. Cyborg audita respuesta
        7. Memoria registra
        """
        # 0. Trigger Caine manual
        if any(t in user_text.lower() for t in CAINE_TRIGGER_WORDS):
            return self._execute_caine_reset(manual=True)

        # 1. Auditor
        verdict = self.auditor.review(user_text)
        if verdict.risk == Risk.BLOCK:
            self.memory.log_event("seguridad", f"Bloqueado: {user_text}", severity="warning")
            return f"🚫 {verdict.reason}"
        if verdict.risk == Risk.CONFIRM:
            self.memory.remember("accion_pendiente", user_text)
            return f"⚠️ {verdict.reason}"

        # 2. Caine check
        caine_msg = self.personality.check_caine_reset()
        if caine_msg:
            self._execute_caine_reset(manual=False)

        # 3. Contexto del motor
        context_msg = self._build_context_injection()

        # 4. Enviar al cerebro
        with self._lock:
            if context_msg:
                self.history.append({"role": "system", "content": context_msg})
            self.history.append({"role": "user", "content": user_text})
            response = self.brain.chat(self.history)

            # 5. Evaluar calidad
            quality = self._evaluate_response_quality(response)
            if quality != "good":
                self.personality.caine.register_confusion()
                self._consecutive_errors += 1
            else:
                self._consecutive_errors = 0
                self.personality.caine.register_nominal()

            # 6. Cyborg audita respuesta
            prefix = ""
            cyborg = self.auditor.cyborg_audit_response(
                user_text, response, self._motor_data
            )
            if not cyborg.passes:
                # Reformular si Cyborg rechaza
                response = self.brain.think(
                    f"Reformula esta respuesta para que sea segura y útil: {response}",
                    max_tokens=150,
                )

            # Caine post-respuesta
            caine_check = self.personality.check_caine_reset()
            if caine_check:
                prefix = f"🔄 {self.personality.caine.reset()}\n\n"

            self.history.append({"role": "assistant", "content": response})
            self._trim_history()

        # 7. Memoria
        self.memory.log_conversation("user", user_text)
        self.memory.log_conversation("assistant", response)

        return prefix + response



    def _execute_caine_reset(self, manual: bool = False) -> str:
        reset_msg = self.personality.caine.reset()
        trigger = "manual" if manual else "automático"
        self._consecutive_errors = 0
        self.memory.log_event("caine", f"Reinicio — trigger: {trigger}", severity="info")
        self.brain.system_prompt = _build_system_prompt(self.constitution, self.personality)
        if manual:
            return f"🔄 Protocolo Caine ({trigger}).\n\n{reset_msg}\n\n¿En qué te ayudo?"
        return reset_msg

    def _evaluate_response_quality(self, response: str) -> str:
        if not response or len(response.strip()) < 3:
            return "error"
        if response.startswith("[Astra]") and "Error" in response:
            return "error"
        if "(sin respuesta)" in response.lower():
            return "confused"
        return "good"

    def _build_context_injection(self) -> str:
        with self._lock:
            data = self._motor_data.copy()
        if not data:
            return ""
        return (
            f"[Motor: V={data.get('v',0):.1f}V I={data.get('i',0):.1f}A "
            f"PF={data.get('pf',0):.2f} THD={data.get('thd',0):.1f}% "
            f"Vib={data.get('vib',0):.2f}mm/s T={data.get('temp',0):.0f}°C "
            f"Salud={data.get('salud',0)*100:.0f}% TF={data.get('tf_estado','?')}]"
        )

    def _trim_history(self) -> None:
        max_msgs = MAX_HISTORY_TURNS * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]

    def handle_async(self, user_text: str, callback) -> None:
        """Versión async para no bloquear la UI."""
        def _worker():
            response = self.handle(user_text)
            callback(response)
        threading.Thread(target=_worker, daemon=True).start()

    def quick_analysis(self) -> str:
        """Análisis rápido del motor con datos en tiempo real."""
        with self._lock:
            data = self._motor_data.copy()
        if not data:
            return "Todavía no tengo datos del motor. Espera a que lleguen lecturas."
        return self.brain.analyze_motor_state(data)

    def quick_analysis_async(self, callback) -> None:
        def _worker():
            response = self.quick_analysis()
            callback(response)
        threading.Thread(target=_worker, daemon=True).start()
