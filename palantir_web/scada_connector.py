"""
Conector SCADA — FALCON CFE.

Se conecta a la red de CFE (SCADA/EMS) para obtener datos REALES en tiempo real.
Soporta múltiples protocolos industriales:

- OPC-UA: el estándar moderno (lo que usa CFE en sistemas nuevos)
- Modbus TCP: protocolo clásico para RTUs y medidores
- REST API: si CFE expone una API HTTP
- MQTT: para dispositivos IoT propios

Configuración: datos/scada_config.json (se crea la primera vez con plantilla)

Si NO hay configuración o la conexión falla, FALCON sigue funcionando
con datos estimados (no se rompe nunca).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime

CONFIG_PATH = Path(__file__).resolve().parent.parent / "datos" / "scada_config.json"
PLANTILLA_PATH = Path(__file__).resolve().parent.parent / "datos" / "scada_config.ejemplo.json"


def _crear_plantilla():
    """Crea el archivo de ejemplo si no existe."""
    if not PLANTILLA_PATH.exists():
        PLANTILLA_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLANTILLA_PATH.write_text(json.dumps({
            "_comentario": "INSTRUCCIONES: Copia este archivo como scada_config.json y llena los datos",
            "_paso1": "Elige el protocolo que usa tu sistema (opc-ua, modbus, rest, mqtt)",
            "_paso2": "Llena la dirección del servidor, usuario y contraseña",
            "_paso3": "Reinicia FALCON — los datos reales reemplazan los simulados",
            "protocolo": "opc-ua",
            "conexion": {
                "servidor": "opc.tcp://IP_DEL_SERVIDOR_SCADA:4840",
                "usuario": "tu_usuario_de_lectura",
                "password": "tu_contraseña",
                "timeout_s": 10
            },
            "nodos": {
                "_comentario": "Lista de puntos/tags que quieres leer del SCADA",
                "generacion_total": "ns=2;s=Sistema.GeneracionTotal_MW",
                "demanda_total": "ns=2;s=Sistema.DemandaTotal_MW",
                "frecuencia": "ns=2;s=Sistema.Frecuencia_Hz",
                "subestaciones": [
                    {
                        "nombre": "Subestacion Hermosillo",
                        "voltaje": "ns=2;s=SE_Hermosillo.Voltaje_kV",
                        "corriente": "ns=2;s=SE_Hermosillo.Corriente_A",
                        "potencia": "ns=2;s=SE_Hermosillo.Potencia_MW",
                        "temperatura": "ns=2;s=SE_Hermosillo.Temperatura_C",
                        "estado": "ns=2;s=SE_Hermosillo.Estado"
                    }
                ]
            },
            "alternativas": {
                "modbus": {
                    "servidor": "IP_DEL_MEDIDOR:502",
                    "registros": {
                        "voltaje": {"direccion": 0, "tipo": "float32"},
                        "corriente": {"direccion": 2, "tipo": "float32"},
                        "potencia": {"direccion": 4, "tipo": "float32"},
                        "frecuencia": {"direccion": 6, "tipo": "float32"}
                    }
                },
                "rest_api": {
                    "url": "https://api.cfe.gob.mx/v1/telemetria",
                    "token": "TU_TOKEN_DE_API",
                    "intervalo_s": 5
                },
                "mqtt": {
                    "broker": "mqtt://IP_DEL_BROKER:1883",
                    "usuario": "falcon",
                    "password": "tu_password",
                    "topics": {
                        "generacion": "cfe/noroeste/generacion",
                        "demanda": "cfe/noroeste/demanda",
                        "alertas": "cfe/noroeste/alertas"
                    }
                }
            }
        }, indent=2, ensure_ascii=False), encoding="utf-8")


def esta_configurado() -> bool:
    """Verifica si hay una configuración SCADA válida."""
    return CONFIG_PATH.exists()


def cargar_config() -> dict | None:
    """Carga la configuración SCADA."""
    if not CONFIG_PATH.exists():
        return None
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if cfg.get("protocolo") and cfg.get("conexion"):
            return cfg
    except Exception:
        pass
    return None


def leer_datos_scada() -> dict | None:
    """
    Lee datos reales del SCADA según el protocolo configurado.
    Retorna un dict con los valores o None si falla/no está configurado.

    Si retorna datos, FALCON los usa en vez de los simulados.
    Si retorna None, FALCON sigue con la simulación (no se rompe).
    """
    cfg = cargar_config()
    if not cfg:
        return None

    protocolo = cfg.get("protocolo", "").lower()

    try:
        if protocolo == "opc-ua":
            return _leer_opcua(cfg)
        elif protocolo == "modbus":
            return _leer_modbus(cfg)
        elif protocolo == "rest":
            return _leer_rest(cfg)
        elif protocolo == "mqtt":
            return _leer_mqtt(cfg)
    except Exception as e:
        print(f"[SCADA] Error al leer ({protocolo}): {e}")

    return None


def _leer_opcua(cfg: dict) -> dict | None:
    """Lee datos vía OPC-UA (el estándar de SCADA moderno)."""
    try:
        from opcua import Client
    except ImportError:
        print("[SCADA] Para OPC-UA instala: pip install opcua")
        return None

    conn = cfg.get("conexion", {})
    nodos = cfg.get("nodos", {})

    client = Client(conn.get("servidor", ""))
    if conn.get("usuario"):
        client.set_user(conn["usuario"])
        client.set_password(conn.get("password", ""))

    client.connect()
    try:
        datos = {"timestamp": datetime.now().isoformat(), "fuente": "scada_opcua"}

        # Leer nodos principales
        if nodos.get("generacion_total"):
            datos["generacion_mw"] = client.get_node(nodos["generacion_total"]).get_value()
        if nodos.get("demanda_total"):
            datos["demanda_mw"] = client.get_node(nodos["demanda_total"]).get_value()
        if nodos.get("frecuencia"):
            datos["frecuencia_hz"] = client.get_node(nodos["frecuencia"]).get_value()

        # Leer subestaciones individuales
        subs = []
        for sub_cfg in nodos.get("subestaciones", []):
            sub = {"nombre": sub_cfg.get("nombre", "")}
            if sub_cfg.get("voltaje"):
                sub["voltaje_kv"] = client.get_node(sub_cfg["voltaje"]).get_value()
            if sub_cfg.get("corriente"):
                sub["corriente_a"] = client.get_node(sub_cfg["corriente"]).get_value()
            if sub_cfg.get("potencia"):
                sub["potencia_mw"] = client.get_node(sub_cfg["potencia"]).get_value()
            if sub_cfg.get("temperatura"):
                sub["temperatura_c"] = client.get_node(sub_cfg["temperatura"]).get_value()
            if sub_cfg.get("estado"):
                sub["estado"] = client.get_node(sub_cfg["estado"]).get_value()
            subs.append(sub)
        datos["subestaciones"] = subs

        return datos
    finally:
        client.disconnect()


def _leer_modbus(cfg: dict) -> dict | None:
    """Lee datos vía Modbus TCP (protocolo clásico para medidores/RTUs)."""
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        print("[SCADA] Para Modbus instala: pip install pymodbus")
        return None

    conn = cfg.get("conexion", {})
    servidor = conn.get("servidor", "127.0.0.1:502")
    host, port = servidor.split(":") if ":" in servidor else (servidor, "502")

    client = ModbusTcpClient(host, port=int(port))
    if not client.connect():
        return None

    try:
        import struct
        registros = cfg.get("nodos", {}).get("registros",
                     cfg.get("alternativas", {}).get("modbus", {}).get("registros", {}))
        datos = {"timestamp": datetime.now().isoformat(), "fuente": "scada_modbus"}

        for nombre, reg in registros.items():
            dir = reg.get("direccion", 0)
            result = client.read_holding_registers(dir, 2)
            if result and not result.isError():
                raw = struct.pack(">HH", *result.registers)
                valor = struct.unpack(">f", raw)[0]
                datos[nombre] = round(valor, 2)

        return datos
    finally:
        client.close()


def _leer_rest(cfg: dict) -> dict | None:
    """Lee datos vía API REST (HTTP)."""
    try:
        import httpx
    except ImportError:
        print("[SCADA] Para REST instala: pip install httpx")
        return None

    rest_cfg = cfg.get("alternativas", {}).get("rest_api", cfg.get("conexion", {}))
    url = rest_cfg.get("url", "")
    token = rest_cfg.get("token", "")

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = httpx.get(url, headers=headers, timeout=10)
    if r.status_code == 200:
        datos = r.json()
        datos["fuente"] = "scada_rest"
        datos["timestamp"] = datetime.now().isoformat()
        return datos
    return None


def _leer_mqtt(cfg: dict) -> dict | None:
    """
    Lee el último dato publicado en MQTT.
    Nota: MQTT es asíncrono, aquí se hace una lectura puntual.
    Para lectura continua se necesita un subscriber separado.
    """
    # MQTT requiere un subscriber corriendo aparte — aquí solo verificamos config
    print("[SCADA] MQTT configurado. Para datos en tiempo real, inicia el subscriber MQTT.")
    return None


# Crear la plantilla de ejemplo al importar el módulo
_crear_plantilla()
