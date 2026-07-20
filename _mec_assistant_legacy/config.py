"""
Configuración del asistente MEC + detección de hardware.

Versión simplificada de Astra: sin modos portátil/residente, enfocada en
auto-escalar el modelo LLM según los recursos disponibles.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "mec.config.json"
ETHICS_PATH = PACKAGE_ROOT / "ethics_industrial.md"


@dataclass
class Hardware:
    """Recursos detectados para auto-escalar el cerebro."""
    ram_gb: float = 0.0
    has_gpu: bool = False
    cpu_count: int = 0
    tier: str = "ligera"  # ligera | recomendada | potente

    @staticmethod
    def detect() -> "Hardware":
        cpu_count = os.cpu_count() or 1
        ram_gb = 0.0
        try:
            import psutil
            ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except Exception:
            pass

        has_gpu = _detect_gpu()

        if ram_gb >= 24 and has_gpu:
            tier = "potente"
        elif ram_gb >= 12:
            tier = "recomendada"
        else:
            tier = "ligera"

        return Hardware(ram_gb=ram_gb, has_gpu=has_gpu, cpu_count=cpu_count, tier=tier)


def _detect_gpu() -> bool:
    """Detección best-effort de GPU dedicada."""
    if any((Path(p) / "nvidia-smi").exists() for p in os.environ.get("PATH", "").split(os.pathsep) if p):
        return True
    if os.environ.get("CUDA_PATH"):
        return True
    return False


@dataclass
class MECConfig:
    raw: dict[str, Any]
    hardware: Hardware

    @property
    def name(self) -> str:
        return self.raw.get("identity", {}).get("name", "MEC")

    @property
    def language(self) -> str:
        return self.raw.get("identity", {}).get("language", "es")

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node


def load_config(path: Path | None = None) -> MECConfig:
    cfg_path = path or DEFAULT_CONFIG_PATH
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except json.JSONDecodeError as exc:
        print(f"[MEC] Config inválida en {cfg_path}: {exc}", file=sys.stderr)
        raw = {}

    hardware = Hardware.detect()
    return MECConfig(raw=raw, hardware=hardware)
