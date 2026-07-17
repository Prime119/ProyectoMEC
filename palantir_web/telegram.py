"""
Notificaciones push por Telegram — FALCON CFE.

Envía alertas críticas a un chat/grupo de Telegram cuando se detectan
fallas, sobrecargas o anomalías.

Configuración:
1. Crea un bot en Telegram (habla con @BotFather → /newbot)
2. Copia el token que te da
3. Crea un archivo datos/telegram_config.json con:
   {"token": "TU_TOKEN", "chat_id": "TU_CHAT_ID"}
4. Para obtener tu chat_id: envía un mensaje al bot y visita
   https://api.telegram.org/botTU_TOKEN/getUpdates

Las alertas se envían automáticamente (críticas y altas).
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "datos" / "telegram_config.json"


def _cargar_config() -> dict | None:
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if cfg.get("token") and cfg.get("chat_id"):
                return cfg
        except Exception:
            pass
    return None


def enviar_alerta(mensaje: str) -> bool:
    """
    Envía un mensaje a Telegram. Retorna True si se envió correctamente.
    Si no está configurado, no hace nada (no rompe el sistema).
    """
    cfg = _cargar_config()
    if not cfg:
        return False
    try:
        import httpx
        url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
        r = httpx.post(url, json={
            "chat_id": cfg["chat_id"],
            "text": f"🦅 FALCON CFE\n\n{mensaje}",
            "parse_mode": "HTML",
        }, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def enviar_alertas_criticas(alertas: list[dict]) -> int:
    """
    Envía las alertas críticas/altas a Telegram.
    Retorna cuántas se enviaron exitosamente.
    """
    cfg = _cargar_config()
    if not cfg:
        return 0
    enviadas = 0
    for a in alertas:
        if a.get("severidad") in ("critica", "alta"):
            if enviar_alerta(a.get("mensaje", "")):
                enviadas += 1
    return enviadas


def esta_configurado() -> bool:
    """Verifica si Telegram está configurado."""
    return _cargar_config() is not None
