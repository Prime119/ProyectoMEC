"""
Simulador de Telemetría en Tiempo Real — Palantir CFE.

Genera datos simulados realistas para cada planta y línea de transmisión.
Los valores varían dinámicamente para simular operación en vivo.
"""
from __future__ import annotations

import random
import time
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .datos_geograficos import (
    PLANTAS_GENERACION, SUBESTACIONES, LINEAS_TRANSMISION,
    CentralGeneracion, Subestacion, LineaTransmision,
    TipoPlanta, EstadoOperativo,
)


@dataclass
class TelemetriaPlanta:
    """Estado en tiempo real de una planta de generación."""
    planta_id: str
    nombre: str
    estado_operativo: EstadoOperativo
    generacion_actual_mw: float       # Generación actual
    capacidad_mw: float               # Capacidad instalada
    factor_planta: float              # 0-1, qué tan cargada está
    temperatura_caldera_c: float      # Temperatura principal
    presion_vapor_mpa: float          # Presión de vapor (si aplica)
    vibracion_turbina_mms: float      # Vibración de la turbina
    rpm_turbina: float                # RPM de la turbina/generador
    voltaje_generador_kv: float       # Voltaje de salida
    frecuencia_hz: float              # Frecuencia eléctrica
    eficiencia_pct: float             # Eficiencia de conversión
    emisiones_co2_ton_h: float        # Emisiones (solo térmicas)
    horas_operacion: int              # Horas acumuladas
    ultima_actualizacion: str
    alertas: list[str] = field(default_factory=list)


@dataclass
class TelemetriaLinea:
    """Estado en tiempo real de una línea de transmisión."""
    linea_id: str
    nombre: str
    estado_operativo: EstadoOperativo
    carga_pct: float                  # % de capacidad utilizada
    flujo_mw: float                   # MW fluyendo por la línea
    capacidad_mw: float
    corriente_a: float                # Corriente en amperes
    temperatura_conductor_c: float    # Temperatura del conductor
    flecha_m: float                   # Sag/flecha del conductor en metros
    perdidas_mw: float                # Pérdidas por transmisión
    frecuencia_hz: float
    voltaje_kv: float                 # Voltaje actual
    voltaje_nominal_kv: float
    proteccion_activa: bool           # Si la protección está disparada
    ultima_falla: str                 # Timestamp de última falla
    ultima_actualizacion: str
    alertas: list[str] = field(default_factory=list)


class SimuladorTelemetria:
    """Motor de simulación de telemetría en tiempo real para toda la infraestructura."""

    def __init__(self):
        self.t0 = time.time()
        self.tick_count = 0

        # Estado persistente por planta
        self._estado_plantas: dict[str, EstadoOperativo] = {}
        self._base_gen: dict[str, float] = {}  # Factor base de generación
        self._falla_timers: dict[str, float] = {}

        # Inicializar estados
        for p in PLANTAS_GENERACION:
            # 85% operando, 10% mantenimiento, 5% arranque
            r = random.random()
            if r < 0.85:
                self._estado_plantas[p.id] = EstadoOperativo.OPERANDO
            elif r < 0.95:
                self._estado_plantas[p.id] = EstadoOperativo.MANTENIMIENTO
            else:
                self._estado_plantas[p.id] = EstadoOperativo.ARRANQUE

            # Factor base según tipo
            if p.tipo == TipoPlanta.SOLAR:
                self._base_gen[p.id] = 0.0  # Depende de hora
            elif p.tipo == TipoPlanta.EOLICA:
                self._base_gen[p.id] = random.uniform(0.2, 0.6)
            elif p.tipo == TipoPlanta.GEOTERMICA:
                self._base_gen[p.id] = random.uniform(0.85, 0.95)
            elif p.tipo == TipoPlanta.HIDROELECTRICA:
                self._base_gen[p.id] = random.uniform(0.3, 0.7)
            else:
                self._base_gen[p.id] = random.uniform(0.5, 0.9)

        # Estado persistente por línea
        self._estado_lineas: dict[str, EstadoOperativo] = {}
        for lt in LINEAS_TRANSMISION:
            self._estado_lineas[lt.id] = EstadoOperativo.OPERANDO

    def tick(self) -> tuple[list[TelemetriaPlanta], list[TelemetriaLinea]]:
        """Actualiza toda la telemetría (llamar cada 1-2 segundos)."""
        self.tick_count += 1
        t = time.time() - self.t0
        hora_actual = datetime.now().hour

        plantas = [self._simular_planta(p, t, hora_actual) for p in PLANTAS_GENERACION]
        lineas = [self._simular_linea(lt, t) for lt in LINEAS_TRANSMISION]

        # Eventos aleatorios (baja probabilidad)
        self._generar_eventos()

        return plantas, lineas

    def _simular_planta(self, p: CentralGeneracion, t: float, hora: int) -> TelemetriaPlanta:
        """Simula la telemetría de una planta."""
        estado = self._estado_plantas[p.id]
        alertas = []

        # Factor de generación basado en tipo y hora
        if estado == EstadoOperativo.MANTENIMIENTO:
            gen_factor = 0.0
        elif estado == EstadoOperativo.ARRANQUE:
            gen_factor = random.uniform(0.1, 0.3)
        elif estado == EstadoOperativo.FALLA:
            gen_factor = 0.0
        else:
            base = self._base_gen[p.id]

            # Solar: depende de hora del día
            if p.tipo == TipoPlanta.SOLAR:
                if 6 <= hora <= 18:
                    solar_curve = math.sin(math.pi * (hora - 6) / 12)
                    base = solar_curve * random.uniform(0.6, 0.95)
                else:
                    base = 0.0

            # Eólica: varía mucho
            elif p.tipo == TipoPlanta.EOLICA:
                base = abs(math.sin(t * 0.01 + hash(p.id) % 100)) * random.uniform(0.15, 0.85)

            # Variación temporal suave
            gen_factor = base + math.sin(t * 0.05 + hash(p.id)) * 0.05
            gen_factor += random.gauss(0, 0.02)
            gen_factor = max(0.0, min(1.0, gen_factor))

        gen_mw = p.capacidad_mw * gen_factor

        # Temperatura de caldera/equipo
        if p.tipo in (TipoPlanta.TERMOELECTRICA, TipoPlanta.CICLO_COMBINADO, TipoPlanta.TURBOGAS):
            temp_base = 480 + gen_factor * 60
            temp = temp_base + math.sin(t * 0.1) * 5 + random.gauss(0, 2)
            presion = 8.0 + gen_factor * 4.0 + random.gauss(0, 0.1)
            emisiones = gen_mw * 0.45 + random.gauss(0, 5)
        elif p.tipo == TipoPlanta.GEOTERMICA:
            temp = 280 + random.gauss(0, 3)
            presion = 6.5 + random.gauss(0, 0.2)
            emisiones = gen_mw * 0.05
        else:
            temp = 35 + gen_factor * 20 + random.gauss(0, 1)
            presion = 0.0
            emisiones = 0.0

        # Vibración de turbina
        if gen_factor > 0:
            vib = 1.5 + gen_factor * 1.2 + random.gauss(0, 0.1)
            rpm = 3600 if p.tipo != TipoPlanta.HIDROELECTRICA else 180 + gen_factor * 120
        else:
            vib = 0.0
            rpm = 0.0

        # Voltaje y frecuencia
        voltaje = 13.8 + random.gauss(0, 0.05) if gen_factor > 0 else 0.0
        freq = 60.0 + random.gauss(0, 0.02) if gen_factor > 0 else 0.0

        # Eficiencia
        if gen_factor > 0.1:
            if p.tipo in (TipoPlanta.CICLO_COMBINADO,):
                eficiencia = 48 + gen_factor * 8 + random.gauss(0, 0.5)
            elif p.tipo == TipoPlanta.TERMOELECTRICA:
                eficiencia = 33 + gen_factor * 5 + random.gauss(0, 0.5)
            elif p.tipo == TipoPlanta.GEOTERMICA:
                eficiencia = 12 + random.gauss(0, 0.3)
            else:
                eficiencia = 85 + random.gauss(0, 1)
        else:
            eficiencia = 0.0

        # Alertas
        if vib > 3.5:
            alertas.append(f"Vibración elevada: {vib:.1f} mm/s")
        if temp > 560 and p.tipo in (TipoPlanta.TERMOELECTRICA, TipoPlanta.CICLO_COMBINADO):
            alertas.append(f"Temperatura crítica caldera: {temp:.0f}°C")
        if gen_factor > 0.95:
            alertas.append("Operando al límite de capacidad")

        return TelemetriaPlanta(
            planta_id=p.id,
            nombre=p.nombre,
            estado_operativo=estado,
            generacion_actual_mw=round(gen_mw, 1),
            capacidad_mw=p.capacidad_mw,
            factor_planta=round(gen_factor, 3),
            temperatura_caldera_c=round(temp, 1),
            presion_vapor_mpa=round(presion, 2),
            vibracion_turbina_mms=round(vib, 2),
            rpm_turbina=round(rpm, 0),
            voltaje_generador_kv=round(voltaje, 2),
            frecuencia_hz=round(freq, 3),
            eficiencia_pct=round(eficiencia, 1),
            emisiones_co2_ton_h=round(max(0, emisiones), 1),
            horas_operacion=random.randint(10000, 120000),
            ultima_actualizacion=datetime.now().strftime("%H:%M:%S"),
            alertas=alertas,
        )

    def _simular_linea(self, lt: LineaTransmision, t: float) -> TelemetriaLinea:
        """Simula la telemetría de una línea de transmisión."""
        estado = self._estado_lineas[lt.id]
        alertas = []

        if estado == EstadoOperativo.FALLA:
            carga_pct = 0.0
        elif estado == EstadoOperativo.MANTENIMIENTO:
            carga_pct = 0.0
        else:
            # Carga varía con demanda (sinusoidal + ruido)
            hora = datetime.now().hour
            # Pico de demanda: 14-20h, mínimo: 2-6h
            demanda_curve = 0.5 + 0.3 * math.sin(math.pi * (hora - 2) / 12)
            carga_pct = demanda_curve + math.sin(t * 0.02 + hash(lt.id)) * 0.08
            carga_pct += random.gauss(0, 0.03)
            carga_pct = max(0.1, min(0.98, carga_pct))

        flujo_mw = lt.capacidad_mw * carga_pct

        # Corriente (I = P / (sqrt(3) * V * cos_phi))
        v_nominal = float(lt.nivel_tension.value.replace(" kV", ""))
        corriente = (flujo_mw * 1000) / (1.732 * v_nominal * 0.95) if v_nominal > 0 else 0

        # Temperatura del conductor (depende de carga y ambiente)
        temp_ambiente = 35 + math.sin(t * 0.005) * 5  # 30-40°C
        temp_conductor = temp_ambiente + carga_pct * 40 + random.gauss(0, 1)

        # Flecha (sag) del conductor — aumenta con temperatura
        flecha_base = 8.0  # metros a 25°C
        flecha = flecha_base + (temp_conductor - 25) * 0.05 + random.gauss(0, 0.1)

        # Pérdidas (I²R, proporcional al cuadrado de la carga)
        perdidas = flujo_mw * carga_pct * 0.02 + random.gauss(0, 0.5)

        # Voltaje actual (puede variar ±5%)
        voltaje_actual = v_nominal * (1 + random.gauss(0, 0.01))

        # Frecuencia
        freq = 60.0 + random.gauss(0, 0.015)

        # Alertas
        if carga_pct > 0.85:
            alertas.append(f"Carga elevada: {carga_pct*100:.0f}%")
        if temp_conductor > 70:
            alertas.append(f"Conductor caliente: {temp_conductor:.0f}°C")
        if flecha > 12:
            alertas.append(f"Flecha excesiva: {flecha:.1f}m — riesgo de contacto")
        if abs(voltaje_actual - v_nominal) / v_nominal > 0.03:
            alertas.append(f"Desviación de voltaje: {voltaje_actual:.1f}kV")

        return TelemetriaLinea(
            linea_id=lt.id,
            nombre=lt.nombre,
            estado_operativo=estado,
            carga_pct=round(carga_pct * 100, 1),
            flujo_mw=round(flujo_mw, 1),
            capacidad_mw=lt.capacidad_mw,
            corriente_a=round(corriente, 1),
            temperatura_conductor_c=round(temp_conductor, 1),
            flecha_m=round(flecha, 2),
            perdidas_mw=round(max(0, perdidas), 2),
            frecuencia_hz=round(freq, 3),
            voltaje_kv=round(voltaje_actual, 1),
            voltaje_nominal_kv=v_nominal,
            proteccion_activa=(estado == EstadoOperativo.FALLA),
            ultima_falla="—",
            ultima_actualizacion=datetime.now().strftime("%H:%M:%S"),
            alertas=alertas,
        )

    def _generar_eventos(self):
        """Genera eventos aleatorios (fallas, recuperaciones)."""
        # 0.5% probabilidad de falla por tick
        if random.random() < 0.005:
            planta = random.choice(PLANTAS_GENERACION)
            if self._estado_plantas[planta.id] == EstadoOperativo.OPERANDO:
                self._estado_plantas[planta.id] = EstadoOperativo.FALLA
                self._falla_timers[planta.id] = time.time()

        # Recuperar plantas en falla después de ~30 segundos
        for pid, t_falla in list(self._falla_timers.items()):
            if time.time() - t_falla > 30:
                self._estado_plantas[pid] = EstadoOperativo.OPERANDO
                del self._falla_timers[pid]

        # 0.2% probabilidad de falla en línea
        if random.random() < 0.002:
            linea = random.choice(LINEAS_TRANSMISION)
            if self._estado_lineas[linea.id] == EstadoOperativo.OPERANDO:
                self._estado_lineas[linea.id] = EstadoOperativo.FALLA

        # Recuperar líneas después de 20 seg
        for lt in LINEAS_TRANSMISION:
            if self._estado_lineas[lt.id] == EstadoOperativo.FALLA:
                if random.random() < 0.05:  # ~5% chance per tick de recuperar
                    self._estado_lineas[lt.id] = EstadoOperativo.OPERANDO

    def get_resumen_sistema(self, plantas_tel: list[TelemetriaPlanta],
                             lineas_tel: list[TelemetriaLinea]) -> dict:
        """Genera un resumen del estado de todo el sistema."""
        gen_total = sum(p.generacion_actual_mw for p in plantas_tel)
        cap_total = sum(p.capacidad_mw for p in plantas_tel)
        plantas_op = sum(1 for p in plantas_tel if p.estado_operativo == EstadoOperativo.OPERANDO)
        plantas_falla = sum(1 for p in plantas_tel if p.estado_operativo == EstadoOperativo.FALLA)
        lineas_op = sum(1 for l in lineas_tel if l.estado_operativo == EstadoOperativo.OPERANDO)
        lineas_falla = sum(1 for l in lineas_tel if l.estado_operativo == EstadoOperativo.FALLA)
        alertas_totales = sum(len(p.alertas) for p in plantas_tel) + sum(len(l.alertas) for l in lineas_tel)

        return {
            "generacion_total_mw": round(gen_total, 0),
            "capacidad_total_mw": round(cap_total, 0),
            "factor_carga_sistema": round(gen_total / cap_total * 100, 1) if cap_total > 0 else 0,
            "plantas_operando": plantas_op,
            "plantas_falla": plantas_falla,
            "plantas_total": len(plantas_tel),
            "lineas_operando": lineas_op,
            "lineas_falla": lineas_falla,
            "lineas_total": len(lineas_tel),
            "alertas_activas": alertas_totales,
            "frecuencia_sistema": round(60.0 + random.gauss(0, 0.01), 3),
            "demanda_estimada_mw": round(gen_total * 0.97, 0),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
