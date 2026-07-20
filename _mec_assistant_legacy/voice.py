"""
Capa 5 — Voz del asistente MEC.

Integra STT (Speech-to-Text) y TTS (Text-to-Speech) para que MEC pueda
escuchar al operador y responder con voz, estilo JARVIS.

STT: faster-whisper (offline, rápido, preciso en español)
TTS: piper-tts (offline, voces naturales en español)

Diseño:
- El operador presiona un botón de micrófono (push-to-talk)
- MEC escucha, transcribe, procesa y responde por texto Y voz
- La voz es opcional — se puede desactivar sin perder funcionalidad
"""
from __future__ import annotations

import subprocess
import threading
import tempfile
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class VoiceConfig:
    """Configuración de voz."""
    stt_model: str = "small"           # tiny | base | small | medium | large
    stt_language: str = "es"
    tts_enabled: bool = True
    tts_voice: str = "es_MX-claude-high"
    tts_voice_path: str = ""           # Ruta al modelo .onnx de piper (si es custom)
    piper_binary: str = "piper"        # Ruta al ejecutable de piper
    sample_rate: int = 16000
    record_seconds: float = 10.0       # Máximo de grabación por turno
    silence_threshold: float = 0.02    # Umbral de silencio para cortar grabación
    silence_duration: float = 1.5      # Segundos de silencio para terminar


class Ear:
    """STT — Oído de MEC (faster-whisper)."""

    def __init__(self, config: VoiceConfig) -> None:
        self.config = config
        self._model = None
        self._available = False
        self._init_model()

    def _init_model(self) -> None:
        """Carga el modelo de whisper."""
        try:
            from faster_whisper import WhisperModel
            device = "cuda" if _has_cuda() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            self._model = WhisperModel(
                self.config.stt_model,
                device=device,
                compute_type=compute_type,
            )
            self._available = True
        except ImportError:
            print("[MEC-Voz] faster-whisper no instalado. STT deshabilitado.")
            self._available = False
        except Exception as e:
            print(f"[MEC-Voz] Error cargando modelo STT: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def listen(self, audio_data=None) -> str:
        """
        Escucha al operador y devuelve el texto transcrito.

        Si audio_data es None, graba desde el micrófono.
        Si se proporciona audio_data (numpy array), transcribe eso directamente.
        """
        if not self._available:
            return ""

        if audio_data is None:
            audio_data = self._record_audio()

        if audio_data is None or len(audio_data) == 0:
            return ""

        try:
            segments, _ = self._model.transcribe(
                audio_data,
                language=self.config.stt_language,
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            return text.strip()
        except Exception as e:
            print(f"[MEC-Voz] Error en transcripción: {e}")
            return ""

    def _record_audio(self):
        """Graba audio desde el micrófono con detección de silencio."""
        try:
            import sounddevice as sd
            import numpy as np

            duration = self.config.record_seconds
            sr = self.config.sample_rate
            silence_thresh = self.config.silence_threshold
            silence_dur = self.config.silence_duration

            print("[MEC-Voz] 🎙️ Escuchando...")
            audio = sd.rec(
                int(duration * sr), samplerate=sr,
                channels=1, dtype='float32'
            )

            # Esperar con detección de silencio
            frames_per_check = int(sr * 0.1)  # Cada 100ms
            silence_frames = 0
            silence_needed = int(silence_dur / 0.1)
            total_frames = int(duration * sr)
            checked = 0

            import time
            while checked < total_frames:
                time.sleep(0.1)
                checked += frames_per_check
                if checked >= len(audio):
                    break
                chunk = audio[max(0, checked - frames_per_check):checked]
                rms = np.sqrt(np.mean(chunk ** 2))
                if rms < silence_thresh:
                    silence_frames += 1
                else:
                    silence_frames = 0
                if silence_frames >= silence_needed and checked > sr:
                    # Silencio detectado y ya grabamos al menos 1 segundo
                    sd.stop()
                    break

            sd.wait()
            # Recortar al audio útil
            audio_trimmed = audio[:checked].flatten()
            return audio_trimmed

        except ImportError:
            print("[MEC-Voz] sounddevice no instalado. No puedo grabar audio.")
            return None
        except Exception as e:
            print(f"[MEC-Voz] Error grabando audio: {e}")
            return None


class Voice:
    """TTS — Voz de MEC (piper-tts)."""

    def __init__(self, config: VoiceConfig) -> None:
        self.config = config
        self._available = False
        self._check_availability()

    def _check_availability(self) -> None:
        """Verifica si piper está disponible."""
        if not self.config.tts_enabled:
            return
        try:
            # Verificar que el binario de piper existe
            result = subprocess.run(
                [self.config.piper_binary, "--help"],
                capture_output=True, timeout=5
            )
            self._available = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Intentar con módulo Python de piper
            try:
                import piper  # noqa: F401
                self._available = True
            except ImportError:
                print("[MEC-Voz] piper-tts no encontrado. TTS deshabilitado.")
                self._available = False

    @property
    def is_available(self) -> bool:
        return self._available and self.config.tts_enabled

    def speak(self, text: str) -> None:
        """Convierte texto a voz y lo reproduce."""
        if not self.is_available:
            return
        # Lanzar en hilo para no bloquear
        threading.Thread(target=self._speak_sync, args=(text,), daemon=True).start()

    def _speak_sync(self, text: str) -> None:
        """Reproduce voz de forma síncrona."""
        try:
            # Crear archivo temporal WAV
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            # Generar audio con piper
            voice_arg = self.config.tts_voice_path or self.config.tts_voice
            cmd = [
                self.config.piper_binary,
                "--model", voice_arg,
                "--output_file", wav_path,
            ]
            proc = subprocess.run(
                cmd, input=text.encode("utf-8"),
                capture_output=True, timeout=30
            )

            if proc.returncode == 0 and os.path.exists(wav_path):
                self._play_audio(wav_path)

            # Limpiar
            if os.path.exists(wav_path):
                os.unlink(wav_path)

        except Exception as e:
            print(f"[MEC-Voz] Error en TTS: {e}")

    def _play_audio(self, wav_path: str) -> None:
        """Reproduce un archivo WAV."""
        try:
            import sounddevice as sd
            import numpy as np

            # Leer WAV con scipy o wave
            try:
                from scipy.io import wavfile
                sr, data = wavfile.read(wav_path)
            except ImportError:
                import wave
                with wave.open(wav_path, 'rb') as wf:
                    sr = wf.getframerate()
                    frames = wf.readframes(wf.getnframes())
                    data = np.frombuffer(frames, dtype=np.int16)

            # Normalizar a float32
            if data.dtype != np.float32:
                data = data.astype(np.float32) / 32768.0

            sd.play(data, sr)
            sd.wait()
        except Exception as e:
            print(f"[MEC-Voz] Error reproduciendo audio: {e}")


class VoiceIO:
    """Interfaz unificada de voz (STT + TTS) para el asistente MEC."""

    def __init__(self, config: VoiceConfig | None = None) -> None:
        self.config = config or VoiceConfig()
        self.ear = Ear(self.config)
        self.voice = Voice(self.config)

    @property
    def stt_available(self) -> bool:
        return self.ear.is_available

    @property
    def tts_available(self) -> bool:
        return self.voice.is_available

    def listen(self) -> str:
        """Graba y transcribe audio del micrófono."""
        return self.ear.listen()

    def speak(self, text: str) -> None:
        """Convierte texto a voz y reproduce."""
        self.voice.speak(text)

    def listen_async(self, callback: Callable[[str], None]) -> None:
        """Escucha en un hilo separado y devuelve texto via callback."""
        def _worker():
            text = self.listen()
            callback(text)
        threading.Thread(target=_worker, daemon=True).start()


def _has_cuda() -> bool:
    """Detecta si hay CUDA disponible."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        pass
    return os.environ.get("CUDA_PATH") is not None
