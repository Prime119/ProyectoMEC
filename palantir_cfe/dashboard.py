"""
Palantir CFE — Dashboard Principal de Monitoreo de Infraestructura.

Interfaz estilo Palantir/SCADA con:
- Mapa interactivo del Noroeste de México (pintado con PyQtGraph)
- Panel de estado del sistema (generación total, demanda, frecuencia)
- Lista de plantas con estado en tiempo real
- Lista de líneas de transmisión con carga
- Feed de alertas en tiempo real
- Chat MEC integrado para consultas inteligentes

Ejecutar: python -m palantir_cfe.dashboard
"""
from __future__ import annotations

import sys
import os
import math
import time
from datetime import datetime

# Silenciar TensorFlow si se importa indirectamente
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QScrollArea, QFrame, QHeaderView, QAbstractItemView,
    QTextEdit, QLineEdit, QSplitter, QTabWidget, QSizePolicy,
)
from PyQt6.QtCore import QTimer, Qt, QPointF
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QPolygonF,
    QLinearGradient, QRadialGradient,
)
import pyqtgraph as pg

from .datos_geograficos import (
    PLANTAS_GENERACION, SUBESTACIONES, LINEAS_TRANSMISION,
    TipoPlanta, EstadoMX, EstadoOperativo, NivelTension,
)
from .simulador_telemetria import (
    SimuladorTelemetria, TelemetriaPlanta, TelemetriaLinea,
)



# === COLORES PALANTIR ===
C_BG = '#0a0e17'
C_PANEL = '#0f1520'
C_BORDER = '#1a2332'
C_TEXT = '#8899aa'
C_TEXT_H = '#e1e8f0'
C_ACCENT = '#00d4ff'
C_GREEN = '#00e676'
C_YELLOW = '#ffd600'
C_ORANGE = '#ff9100'
C_RED = '#ff1744'
C_PURPLE = '#aa00ff'
C_BLUE = '#2979ff'
C_GRID = '#141e2d'

# Colores por tipo de planta
COLOR_TIPO = {
    TipoPlanta.TERMOELECTRICA: '#ff5252',
    TipoPlanta.CICLO_COMBINADO: '#ff9100',
    TipoPlanta.GEOTERMICA: '#aa00ff',
    TipoPlanta.SOLAR: '#ffd600',
    TipoPlanta.EOLICA: '#00e5ff',
    TipoPlanta.TURBOGAS: '#ff6d00',
    TipoPlanta.HIDROELECTRICA: '#2979ff',
}

# Colores por estado operativo
COLOR_ESTADO = {
    EstadoOperativo.OPERANDO: C_GREEN,
    EstadoOperativo.MANTENIMIENTO: C_YELLOW,
    EstadoOperativo.FALLA: C_RED,
    EstadoOperativo.FUERA_LINEA: '#555555',
    EstadoOperativo.ARRANQUE: C_ORANGE,
}

pg.setConfigOption('background', C_BG)
pg.setConfigOption('foreground', C_TEXT)
pg.setConfigOptions(antialias=True)

STYLE = f"""
QMainWindow, QWidget {{ background: {C_BG}; color: {C_TEXT}; font-family: 'Segoe UI', sans-serif; }}
QLabel {{ color: {C_TEXT}; border: none; }}
QTableWidget {{ background: {C_PANEL}; alternate-background-color: #121a28; color: {C_TEXT_H};
    gridline-color: {C_BORDER}; font-family: 'Consolas'; font-size: 10px; border: none; }}
QTableWidget QHeaderView::section {{ background: #141e2d; color: {C_ACCENT};
    font-size: 9px; font-weight: bold; padding: 4px; border: none; border-bottom: 1px solid {C_BORDER}; }}
QScrollBar:vertical {{ background: {C_BG}; width: 6px; }}
QScrollBar::handle:vertical {{ background: #2a3a4a; border-radius: 3px; }}
QTabWidget::pane {{ border: 1px solid {C_BORDER}; background: {C_PANEL}; }}
QTabBar::tab {{ background: #141e2d; color: {C_TEXT}; padding: 6px 14px; border: none; }}
QTabBar::tab:selected {{ background: {C_PANEL}; color: {C_ACCENT}; border-bottom: 2px solid {C_ACCENT}; }}
QPushButton {{ background: #141e2d; border: 1px solid {C_BORDER}; color: {C_TEXT};
    padding: 5px 12px; border-radius: 3px; font-weight: bold; }}
QPushButton:hover {{ background: #1e2e3e; color: {C_TEXT_H}; }}
QLineEdit {{ background: #0d1520; border: 1px solid {C_BORDER}; color: {C_TEXT_H};
    font-family: 'Consolas'; padding: 6px; border-radius: 3px; }}
QTextEdit {{ background: #0a0e14; color: {C_TEXT_H}; border: 1px solid {C_BORDER};
    font-family: 'Consolas'; font-size: 10px; }}
"""



# === MAPA WIDGET ===
class MapaNoroeste(pg.PlotWidget):
    """Mapa interactivo del Noroeste de México con plantas y líneas."""

    # Bounds del mapa (lon, lat)
    LON_MIN, LON_MAX = -118.0, -105.0
    LAT_MIN, LAT_MAX = 22.5, 33.0

    def __init__(self):
        super().__init__()
        self.setBackground(C_BG)
        self.setAspectLocked(True)
        self.showGrid(x=True, y=True, alpha=0.05)
        self.getAxis('left').setTextPen(C_TEXT)
        self.getAxis('bottom').setTextPen(C_TEXT)
        self.getAxis('left').setPen(C_BORDER)
        self.getAxis('bottom').setPen(C_BORDER)
        self.setXRange(self.LON_MIN, self.LON_MAX)
        self.setYRange(self.LAT_MIN, self.LAT_MAX)
        self.setLabel('bottom', 'Longitud')
        self.setLabel('left', 'Latitud')

        # Dibujar contorno de estados (simplificado)
        self._draw_state_borders()

        # Scatter plots para plantas y subestaciones
        self.scatter_plantas = pg.ScatterPlotItem(size=12, pen=pg.mkPen(None))
        self.addItem(self.scatter_plantas)

        self.scatter_subs = pg.ScatterPlotItem(size=7, pen=pg.mkPen(C_ACCENT, width=1),
                                                brush=pg.mkBrush('#00000000'), symbol='s')
        self.addItem(self.scatter_subs)

        # Líneas de transmisión
        self.line_items: list[pg.PlotCurveItem] = []

        # Labels de estados
        self._draw_state_labels()

        # Inicializar elementos estáticos
        self._draw_subestaciones()
        self._draw_lineas_base()

    def _draw_state_borders(self):
        """Dibuja los bordes simplificados de los estados."""
        # Contorno simplificado de cada estado (puntos clave de la frontera)
        borders = {
            "Baja California": [(-117.1, 32.7), (-115.0, 32.7), (-114.7, 31.3),
                                (-116.1, 28.0), (-117.1, 28.0), (-117.1, 32.7)],
            "BCS": [(-116.1, 28.0), (-114.7, 28.0), (-109.9, 23.0),
                    (-112.0, 23.0), (-116.1, 28.0)],
            "Sonora": [(-115.0, 32.7), (-109.0, 31.3), (-109.0, 26.5),
                       (-112.0, 26.5), (-114.7, 28.0), (-114.7, 31.3), (-115.0, 32.7)],
            "Chihuahua": [(-109.0, 31.3), (-106.0, 31.8), (-105.0, 29.5),
                          (-106.5, 26.0), (-109.0, 26.5), (-109.0, 31.3)],
            "Sinaloa": [(-109.0, 26.5), (-106.5, 26.0), (-105.5, 23.2),
                        (-106.5, 22.5), (-109.5, 22.5), (-109.0, 26.5)],
        }
        for name, pts in borders.items():
            x = [p[0] for p in pts]
            y = [p[1] for p in pts]
            self.plot(x, y, pen=pg.mkPen(C_BORDER, width=1, style=Qt.PenStyle.DashLine))

    def _draw_state_labels(self):
        """Agrega los nombres de los estados al mapa."""
        labels = [
            ("BAJA\nCALIFORNIA", -116.2, 30.5),
            ("B.C.S.", -112.5, 25.0),
            ("SONORA", -111.0, 29.5),
            ("CHIHUAHUA", -106.8, 29.0),
            ("SINALOA", -107.5, 24.5),
        ]
        for text, lon, lat in labels:
            lbl = pg.TextItem(text, color=QColor(C_TEXT), anchor=(0.5, 0.5))
            lbl.setPos(lon, lat)
            font = QFont('Segoe UI', 9, QFont.Weight.Bold)
            lbl.setFont(font)
            self.addItem(lbl)

    def _draw_subestaciones(self):
        """Dibuja las subestaciones como cuadrados."""
        spots = []
        for s in SUBESTACIONES:
            spots.append({
                'pos': (s.lon, s.lat),
                'size': 6,
                'pen': pg.mkPen(C_ACCENT, width=1),
                'brush': pg.mkBrush('#00d4ff33'),
                'symbol': 's',
            })
        self.scatter_subs.setData(spots)

    def _draw_lineas_base(self):
        """Dibuja las líneas de transmisión."""
        for lt in LINEAS_TRANSMISION:
            # Buscar coordenadas origen/destino
            orig = self._find_coords(lt.origen_id)
            dest = self._find_coords(lt.destino_id)
            if orig and dest:
                pen_color = C_GREEN if lt.nivel_tension == NivelTension.KV_400 else C_ACCENT
                width = 2 if lt.nivel_tension == NivelTension.KV_400 else 1
                line = self.plot(
                    [orig[0], dest[0]], [orig[1], dest[1]],
                    pen=pg.mkPen(pen_color, width=width, style=Qt.PenStyle.SolidLine)
                )
                self.line_items.append(line)

    def _find_coords(self, node_id: str) -> tuple[float, float] | None:
        """Busca las coordenadas de un nodo (planta o subestación)."""
        for s in SUBESTACIONES:
            if s.id == node_id:
                return (s.lon, s.lat)
        for p in PLANTAS_GENERACION:
            if p.id == node_id:
                return (p.lon, p.lat)
        return None

    def update_plantas(self, telemetria: list[TelemetriaPlanta]):
        """Actualiza los colores de las plantas según su estado."""
        spots = []
        for i, p in enumerate(PLANTAS_GENERACION):
            tel = telemetria[i] if i < len(telemetria) else None
            if tel:
                color = COLOR_ESTADO.get(tel.estado_operativo, C_TEXT)
                size = 10 + tel.factor_planta * 6  # Más grande si genera más
            else:
                color = C_TEXT
                size = 8
            spots.append({
                'pos': (p.lon, p.lat),
                'size': size,
                'pen': pg.mkPen(color, width=1.5),
                'brush': pg.mkBrush(color + '88'),
                'symbol': 'o',
            })
        self.scatter_plantas.setData(spots)

    def update_lineas(self, telemetria: list[TelemetriaLinea]):
        """Actualiza los colores de las líneas según su carga."""
        for i, line_item in enumerate(self.line_items):
            if i < len(telemetria):
                tel = telemetria[i]
                if tel.estado_operativo == EstadoOperativo.FALLA:
                    color = C_RED
                    width = 3
                elif tel.carga_pct > 85:
                    color = C_ORANGE
                    width = 2.5
                elif tel.carga_pct > 70:
                    color = C_YELLOW
                    width = 2
                else:
                    color = C_GREEN
                    width = 1.5
                line_item.setPen(pg.mkPen(color, width=width))



# === DASHBOARD PRINCIPAL ===
class PalantirCFE(QMainWindow):
    """Ventana principal del dashboard tipo Palantir para CFE Noroeste."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PALANTIR CFE — Infraestructura Eléctrica Noroeste de México")
        self.setMinimumSize(1400, 800)
        self.resize(1600, 900)
        self.setStyleSheet(STYLE)

        # Motor de simulación
        self.sim = SimuladorTelemetria()
        self.plantas_tel: list[TelemetriaPlanta] = []
        self.lineas_tel: list[TelemetriaLinea] = []
        self.alertas_historial: list[str] = []

        # MEC Assistant (opcional)
        self.mec_assistant = None
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from mec_assistant import MECAssistant
            self.mec_assistant = MECAssistant.boot()
            print("🤖 MEC integrado en Palantir CFE")
        except Exception as e:
            print(f"⚠️ MEC no disponible: {e}")

        self._build_ui()

        # Timer de actualización (cada 2 segundos)
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_loop)
        self.timer.start(2000)

        # Primera actualización
        self._update_loop()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main_lay = QVBoxLayout(root)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Top bar
        main_lay.addWidget(self._build_topbar())

        # Body: splitter horizontal
        body_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Izquierda: Mapa + KPIs
        left_widget = QWidget()
        left_lay = QVBoxLayout(left_widget)
        left_lay.setContentsMargins(4, 4, 4, 4)
        left_lay.setSpacing(4)
        left_lay.addWidget(self._build_kpi_bar())
        # Mapa principal: intentar OSINT (Leaflet/WebEngine), si no, usar pyqtgraph
        self._mapa_es_osint = False
        try:
            from .mapa_osint import MapaOSINT, WEBENGINE_DISPONIBLE
            if not WEBENGINE_DISPONIBLE:
                raise ImportError("PyQt6-WebEngine no disponible")
            self.mapa = MapaOSINT()
            self.mapa.activoSeleccionado.connect(self._on_activo_mapa)
            self._mapa_es_osint = True
            print("🗺️ Mapa OSINT (Leaflet) activo")
        except Exception as e:
            print(f"⚠️ Mapa OSINT no disponible ({e}). Usando mapa pyqtgraph.")
            self.mapa = MapaNoroeste()
        left_lay.addWidget(self.mapa, 1)
        body_splitter.addWidget(left_widget)

        # Derecha: Tabs (Plantas, Líneas, Alertas, MEC)
        right_widget = QWidget()
        right_widget.setMaximumWidth(760)
        right_lay = QVBoxLayout(right_widget)
        right_lay.setContentsMargins(4, 4, 4, 4)
        right_lay.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tab_plantas(), "⚡ PLANTAS")
        self.tabs.addTab(self._build_tab_lineas(), "🔌 LÍNEAS")
        self.tabs.addTab(self._build_tab_alertas(), "🚨 ALERTAS")
        self.tabs.addTab(self._build_tab_mec(), "🤖 MEC")
        self.tabs.addTab(self._build_tab_satelite(), "🛰️ SATÉLITE")
        self.tabs.addTab(self._build_tab_3d(), "🧊 3D")
        right_lay.addWidget(self.tabs)
        body_splitter.addWidget(right_widget)

        body_splitter.setSizes([950, 650])
        main_lay.addWidget(body_splitter, 1)

    def _build_topbar(self):
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"background: {C_PANEL}; border-bottom: 1px solid {C_BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)

        lbl_logo = QLabel("PALANTIR")
        lbl_logo.setStyleSheet(f"color: {C_ACCENT}; font-size: 16px; font-weight: 900; letter-spacing: 2px;")
        lbl_sub = QLabel(" / CFE NOROESTE — Monitoreo de Infraestructura en Tiempo Real")
        lbl_sub.setStyleSheet(f"color: {C_TEXT}; font-size: 11px;")

        self.lbl_clock = QLabel("")
        self.lbl_clock.setStyleSheet(f"color: {C_TEXT_H}; font-family: 'Consolas'; font-size: 12px;")

        self.lbl_freq = QLabel("60.000 Hz")
        self.lbl_freq.setStyleSheet(f"color: {C_GREEN}; font-size: 11px; font-weight: bold;")

        lay.addWidget(lbl_logo)
        lay.addWidget(lbl_sub)
        lay.addStretch()
        lay.addWidget(self.lbl_freq)
        lay.addSpacing(20)
        lay.addWidget(self.lbl_clock)
        return bar

    def _build_kpi_bar(self):
        """Barra de KPIs principales del sistema."""
        w = QWidget()
        w.setFixedHeight(70)
        w.setStyleSheet(f"background: {C_PANEL}; border: 1px solid {C_BORDER}; border-radius: 4px;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(20)

        self.kpi_gen = self._make_kpi("GENERACIÓN", "0 MW", C_GREEN)
        self.kpi_demanda = self._make_kpi("DEMANDA", "0 MW", C_ACCENT)
        self.kpi_factor = self._make_kpi("FACTOR CARGA", "0%", C_YELLOW)
        self.kpi_plantas_op = self._make_kpi("PLANTAS OP.", "0/0", C_GREEN)
        self.kpi_lineas_op = self._make_kpi("LÍNEAS OP.", "0/0", C_GREEN)
        self.kpi_alertas = self._make_kpi("ALERTAS", "0", C_RED)

        for kpi in [self.kpi_gen, self.kpi_demanda, self.kpi_factor,
                    self.kpi_plantas_op, self.kpi_lineas_op, self.kpi_alertas]:
            lay.addWidget(kpi)

        return w

    def _make_kpi(self, title: str, value: str, color: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"color: {C_TEXT}; font-size: 9px; font-weight: bold; letter-spacing: 0.5px;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold; font-family: 'Consolas';")
        lbl_v.setObjectName("kpi_value")
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        return w

    def _update_kpi(self, kpi_widget: QWidget, value: str, color: str = None):
        lbl = kpi_widget.findChild(QLabel, "kpi_value")
        if lbl:
            lbl.setText(value)
            if color:
                lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold; font-family: 'Consolas';")


    def _build_tab_plantas(self):
        """Tab con tabla de plantas de generación."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)

        headers = ["Planta", "Estado", "Tipo", "Gen (MW)", "Cap (MW)", "%", "Temp", "Vib", "Estado"]
        self.tbl_plantas = QTableWidget(len(PLANTAS_GENERACION), len(headers))
        self.tbl_plantas.setHorizontalHeaderLabels(headers)
        self.tbl_plantas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_plantas.verticalHeader().setVisible(False)
        self.tbl_plantas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_plantas.setAlternatingRowColors(True)
        self.tbl_plantas.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        for r in range(len(PLANTAS_GENERACION)):
            self.tbl_plantas.setRowHeight(r, 22)

        lay.addWidget(self.tbl_plantas)
        return w

    def _build_tab_lineas(self):
        """Tab con tabla de líneas de transmisión."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)

        headers = ["Línea", "Tensión", "Carga%", "Flujo MW", "Corriente", "Temp°C", "Estado"]
        self.tbl_lineas = QTableWidget(len(LINEAS_TRANSMISION), len(headers))
        self.tbl_lineas.setHorizontalHeaderLabels(headers)
        self.tbl_lineas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_lineas.verticalHeader().setVisible(False)
        self.tbl_lineas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_lineas.setAlternatingRowColors(True)
        self.tbl_lineas.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        for r in range(len(LINEAS_TRANSMISION)):
            self.tbl_lineas.setRowHeight(r, 24)

        lay.addWidget(self.tbl_lineas)
        return w

    def _build_tab_alertas(self):
        """Tab con feed de alertas en tiempo real."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)

        lbl = QLabel("ALERTAS EN TIEMPO REAL")
        lbl.setStyleSheet(f"color: {C_RED}; font-size: 11px; font-weight: bold;")
        lay.addWidget(lbl)

        self.txt_alertas = QTextEdit()
        self.txt_alertas.setReadOnly(True)
        self.txt_alertas.setStyleSheet(f"""
            QTextEdit {{ background: #080c12; color: {C_TEXT_H}; border: 1px solid {C_BORDER};
            font-family: 'Consolas'; font-size: 10px; }}
        """)
        lay.addWidget(self.txt_alertas)
        return w

    def _build_tab_mec(self):
        """Tab con el asistente MEC integrado."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        header = QLabel("🤖 MEC — ASISTENTE DE INFRAESTRUCTURA")
        header.setStyleSheet(f"color: {C_PURPLE}; font-size: 11px; font-weight: bold;")
        lay.addWidget(header)

        self.txt_mec = QTextEdit()
        self.txt_mec.setReadOnly(True)
        self.txt_mec.setStyleSheet(f"""
            QTextEdit {{ background: #080c12; color: {C_TEXT_H}; border: 1px solid {C_PURPLE};
            font-family: 'Consolas'; font-size: 10px; padding: 4px; }}
        """)
        lay.addWidget(self.txt_mec, 1)

        # Input + botones
        input_lay = QHBoxLayout()
        self.input_mec = QLineEdit()
        self.input_mec.setPlaceholderText("Pregunta sobre la infraestructura... (Ej: '¿qué plantas están en falla?')")
        self.input_mec.returnPressed.connect(self._mec_send)
        btn_send = QPushButton("ENVIAR")
        btn_send.setStyleSheet(f"background: {C_PURPLE}; color: #000; font-weight: bold; border: none; padding: 6px 14px;")
        btn_send.clicked.connect(self._mec_send)
        btn_resumen = QPushButton("📊 RESUMEN")
        btn_resumen.clicked.connect(self._mec_resumen)
        input_lay.addWidget(self.input_mec, 1)
        input_lay.addWidget(btn_send)
        input_lay.addWidget(btn_resumen)
        lay.addLayout(input_lay)

        # Mensaje inicial
        self._mec_msg("MEC", "Listo, ingeniero. Tengo vista completa de la infraestructura del Noroeste. "
                      "Pregúntame sobre plantas, líneas, alertas, o pide un resumen del sistema.")
        return w

    def _build_tab_satelite(self):
        """Tab con el visor satelital y detección IA de infraestructura."""
        from .visor_satelital import VisorSatelital
        # Permitir cargar un modelo ONNX vía variable de entorno
        modelo = os.environ.get("PALANTIR_MODELO_ONNX")
        self.visor_sat = VisorSatelital(modelo_onnx=modelo)
        return self.visor_sat

    def _build_tab_3d(self):
        """Tab con el gemelo digital 3D holográfico de las estructuras CFE."""
        try:
            from .vista_3d import Vista3D
            self.vista_3d = Vista3D()
            return self.vista_3d
        except Exception as e:
            from PyQt6.QtWidgets import QLabel
            self.vista_3d = None
            lbl = QLabel(f"Vista 3D no disponible: {e}\n\n"
                         "Instala: pip install PyOpenGL PyOpenGL_accelerate")
            lbl.setStyleSheet(f"color:{C_TEXT}; padding:40px;")
            lbl.setWordWrap(True)
            return lbl


    # === UPDATE LOOP ===
    def _update_loop(self):
        """Actualiza toda la telemetría cada 2 segundos."""
        self.plantas_tel, self.lineas_tel = self.sim.tick()
        resumen = self.sim.get_resumen_sistema(self.plantas_tel, self.lineas_tel)

        # Actualizar reloj
        self.lbl_clock.setText(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self.lbl_freq.setText(f"{resumen['frecuencia_sistema']:.3f} Hz")

        # Actualizar KPIs
        self._update_kpi(self.kpi_gen, f"{resumen['generacion_total_mw']:.0f} MW", C_GREEN)
        self._update_kpi(self.kpi_demanda, f"{resumen['demanda_estimada_mw']:.0f} MW", C_ACCENT)
        fc = resumen['factor_carga_sistema']
        fc_color = C_GREEN if fc < 70 else (C_YELLOW if fc < 85 else C_RED)
        self._update_kpi(self.kpi_factor, f"{fc:.1f}%", fc_color)
        self._update_kpi(self.kpi_plantas_op,
                         f"{resumen['plantas_operando']}/{resumen['plantas_total']}",
                         C_GREEN if resumen['plantas_falla'] == 0 else C_RED)
        self._update_kpi(self.kpi_lineas_op,
                         f"{resumen['lineas_operando']}/{resumen['lineas_total']}",
                         C_GREEN if resumen['lineas_falla'] == 0 else C_RED)
        n_alertas = resumen['alertas_activas']
        self._update_kpi(self.kpi_alertas, str(n_alertas),
                         C_GREEN if n_alertas == 0 else (C_YELLOW if n_alertas < 5 else C_RED))

        # Actualizar mapa (OSINT Leaflet o pyqtgraph según disponibilidad)
        if self._mapa_es_osint:
            estados_activos = {}
            for t in self.plantas_tel:
                estados_activos[t.planta_id] = {
                    "estado": t.estado_operativo.value,
                    "escala": t.factor_planta,
                    "info": f"{t.generacion_actual_mw:.0f}/{t.capacidad_mw:.0f} MW · "
                            f"{t.temperatura_caldera_c:.0f}°C · vib {t.vibracion_turbina_mms:.1f}",
                }
            estados_lineas = {}
            for t in self.lineas_tel:
                estados_lineas[t.linea_id] = {
                    "carga": t.carga_pct,
                    "estado": t.estado_operativo.value,
                }
            self.mapa.actualizar_estados(estados_activos, estados_lineas)
        else:
            self.mapa.update_plantas(self.plantas_tel)
            self.mapa.update_lineas(self.lineas_tel)

        # Actualizar tabla de plantas
        self._update_tabla_plantas()

        # Actualizar tabla de líneas
        self._update_tabla_lineas()

        # Actualizar alertas
        self._update_alertas()

        # Alimentar la vista 3D con telemetría real (si está activa)
        if getattr(self, "vista_3d", None) is not None:
            try:
                gen_mw = resumen['generacion_total_mw'] / max(resumen['plantas_operando'], 1)
                temp = 480 + (resumen['factor_carga_sistema'] - 60) * 2
                vib = 1.5 + resumen['alertas_activas'] * 0.15
                self.vista_3d.actualizar_telemetria_externa(gen_mw, temp, vib)
            except Exception:
                pass

        # Alimentar datos a MEC
        if self.mec_assistant:
            self.mec_assistant.update_motor_data({
                'v': 230.0, 'i': 100.0,
                'p': resumen['generacion_total_mw'],
                'q': 0, 's': 0, 'pf': 0.95,
                'thd': 2.5, 'vib': 1.5, 'freq': resumen['frecuencia_sistema'],
                'temp': 45.0, 'salud': 0.92,
                'tf_estado': 'NOMINAL',
                'ae_loss': 0.001, 'pred_salud': 92.0,
                'n_anomalias': resumen['plantas_falla'],
                'anomaly_score': 0.5,
                # Datos extra para Palantir
                'generacion_total_mw': resumen['generacion_total_mw'],
                'demanda_mw': resumen['demanda_estimada_mw'],
                'plantas_falla': resumen['plantas_falla'],
                'lineas_falla': resumen['lineas_falla'],
                'alertas_activas': n_alertas,
            })

    def _update_tabla_plantas(self):
        for r, tel in enumerate(self.plantas_tel):
            color_est = COLOR_ESTADO.get(tel.estado_operativo, C_TEXT)
            planta = PLANTAS_GENERACION[r]
            color_tipo = COLOR_TIPO.get(planta.tipo, C_TEXT)

            items = [
                (tel.nombre[:30], C_TEXT_H),
                (planta.estado.value[:5], C_TEXT),
                (planta.tipo.value[:12], color_tipo),
                (f"{tel.generacion_actual_mw:.0f}", C_GREEN if tel.generacion_actual_mw > 0 else C_TEXT),
                (f"{tel.capacidad_mw:.0f}", C_TEXT),
                (f"{tel.factor_planta*100:.0f}%", color_est),
                (f"{tel.temperatura_caldera_c:.0f}°C", C_RED if tel.temperatura_caldera_c > 550 else C_TEXT),
                (f"{tel.vibracion_turbina_mms:.1f}", C_ORANGE if tel.vibracion_turbina_mms > 3 else C_TEXT),
                (tel.estado_operativo.value, color_est),
            ]
            for c, (text, color) in enumerate(items):
                item = self.tbl_plantas.item(r, c)
                if item is None:
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tbl_plantas.setItem(r, c, item)
                else:
                    item.setText(text)
                item.setForeground(QColor(color))

    def _update_tabla_lineas(self):
        for r, tel in enumerate(self.lineas_tel):
            color_carga = C_GREEN if tel.carga_pct < 70 else (C_YELLOW if tel.carga_pct < 85 else C_RED)
            color_est = COLOR_ESTADO.get(tel.estado_operativo, C_TEXT)

            items = [
                (tel.nombre[:35], C_TEXT_H),
                (f"{tel.voltaje_nominal_kv:.0f}kV", C_ACCENT),
                (f"{tel.carga_pct:.0f}%", color_carga),
                (f"{tel.flujo_mw:.0f}", C_TEXT_H),
                (f"{tel.corriente_a:.0f}A", C_TEXT),
                (f"{tel.temperatura_conductor_c:.0f}°C", C_ORANGE if tel.temperatura_conductor_c > 65 else C_TEXT),
                (tel.estado_operativo.value, color_est),
            ]
            for c, (text, color) in enumerate(items):
                item = self.tbl_lineas.item(r, c)
                if item is None:
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tbl_lineas.setItem(r, c, item)
                else:
                    item.setText(text)
                item.setForeground(QColor(color))

    def _update_alertas(self):
        """Actualiza el feed de alertas."""
        nuevas = []
        ts = datetime.now().strftime("%H:%M:%S")
        for tel in self.plantas_tel:
            for alerta in tel.alertas:
                nuevas.append(f"[{ts}] ⚡ {tel.nombre}: {alerta}")
            if tel.estado_operativo == EstadoOperativo.FALLA:
                nuevas.append(f"[{ts}] 🚨 FALLA en {tel.nombre}")
        for tel in self.lineas_tel:
            for alerta in tel.alertas:
                nuevas.append(f"[{ts}] 🔌 {tel.nombre}: {alerta}")
            if tel.estado_operativo == EstadoOperativo.FALLA:
                nuevas.append(f"[{ts}] 🚨 LÍNEA FUERA: {tel.nombre}")

        for msg in nuevas:
            if msg not in self.alertas_historial[-20:]:
                self.alertas_historial.append(msg)
                color = C_RED if "🚨" in msg else (C_ORANGE if "⚡" in msg else C_YELLOW)
                self.txt_alertas.append(f'<span style="color:{color};">{msg}</span>')

        # Limitar historial
        if len(self.alertas_historial) > 200:
            self.alertas_historial = self.alertas_historial[-100:]


    # === MEC INTEGRATION ===
    def _on_activo_mapa(self, activo_id: str):
        """Al hacer clic en un activo del mapa OSINT: abre su gemelo digital 3D."""
        if getattr(self, "vista_3d", None) is not None:
            combo = self.vista_3d.combo
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data and data[0] == activo_id:
                    combo.setCurrentIndex(i)
                    # Cambiar a la pestaña 3D
                    for t in range(self.tabs.count()):
                        if "3D" in self.tabs.tabText(t):
                            self.tabs.setCurrentIndex(t)
                            break
                    break

    def _mec_msg(self, sender: str, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        if sender == "MEC":
            color = C_PURPLE
        elif sender == "TÚ":
            color = C_ACCENT
        else:
            color = C_TEXT
        self.txt_mec.append(
            f'<span style="color:{C_TEXT};font-size:9px;">[{ts}]</span> '
            f'<span style="color:{color};font-weight:bold;">{sender}:</span> '
            f'<span style="color:{C_TEXT_H};">{text}</span>'
        )

    def _mec_send(self):
        text = self.input_mec.text().strip()
        if not text:
            return
        self.input_mec.clear()
        self._mec_msg("TÚ", text)

        if not self.mec_assistant:
            self._mec_msg("SISTEMA", "Astra no disponible. Ejecuta: python llama-cpp/setup.py")
            return

        # Inyectar contexto de infraestructura
        contexto = self._build_infra_context()
        full_text = f"[INFRAESTRUCTURA CFE NOROESTE]\n{contexto}\n\n[PREGUNTA DEL OPERADOR]\n{text}"

        def on_response(response):
            QTimer.singleShot(0, lambda: self._mec_msg("MEC", response))

        self.mec_assistant.handle_async(full_text, on_response)

    def _mec_resumen(self):
        """Pide a MEC un resumen del estado del sistema."""
        self._mec_msg("TÚ", "[Resumen del sistema]")
        if not self.mec_assistant:
            # Generar resumen local
            resumen = self.sim.get_resumen_sistema(self.plantas_tel, self.lineas_tel)
            plantas_falla = [t.nombre for t in self.plantas_tel if t.estado_operativo == EstadoOperativo.FALLA]
            lineas_falla = [t.nombre for t in self.lineas_tel if t.estado_operativo == EstadoOperativo.FALLA]
            msg = (
                f"Generación: {resumen['generacion_total_mw']:.0f}/{resumen['capacidad_total_mw']:.0f} MW "
                f"({resumen['factor_carga_sistema']:.1f}%) | "
                f"Plantas: {resumen['plantas_operando']}/{resumen['plantas_total']} operando | "
                f"Líneas: {resumen['lineas_operando']}/{resumen['lineas_total']} operando | "
                f"Alertas: {resumen['alertas_activas']}"
            )
            if plantas_falla:
                msg += f"\n🚨 Plantas en falla: {', '.join(plantas_falla)}"
            if lineas_falla:
                msg += f"\n🚨 Líneas fuera: {', '.join(lineas_falla)}"
            self._mec_msg("MEC", msg)
            return

        contexto = self._build_infra_context()
        prompt = (
            f"[INFRAESTRUCTURA CFE NOROESTE — RESUMEN]\n{contexto}\n\n"
            "Dame un resumen ejecutivo del estado de toda la infraestructura. "
            "Incluye: generación total, plantas con problemas, líneas sobrecargadas, "
            "y si hay alguna situación que requiera atención inmediata. "
            "Sé conciso pero completo (máximo 8 líneas)."
        )

        def on_response(response):
            QTimer.singleShot(0, lambda: self._mec_msg("MEC", response))

        self.mec_assistant.handle_async(prompt, on_response)

    def _build_infra_context(self) -> str:
        """Construye el contexto de infraestructura para MEC."""
        resumen = self.sim.get_resumen_sistema(self.plantas_tel, self.lineas_tel)
        plantas_falla = [f"{t.nombre} ({t.estado_operativo.value})" for t in self.plantas_tel
                         if t.estado_operativo != EstadoOperativo.OPERANDO]
        lineas_problema = [f"{t.nombre} (carga={t.carga_pct:.0f}%)" for t in self.lineas_tel
                           if t.carga_pct > 80 or t.estado_operativo == EstadoOperativo.FALLA]
        top_gen = sorted(self.plantas_tel, key=lambda x: x.generacion_actual_mw, reverse=True)[:5]

        ctx = (
            f"Generación total: {resumen['generacion_total_mw']:.0f} MW / "
            f"{resumen['capacidad_total_mw']:.0f} MW instalados "
            f"(factor={resumen['factor_carga_sistema']:.1f}%)\n"
            f"Frecuencia: {resumen['frecuencia_sistema']:.3f} Hz\n"
            f"Plantas operando: {resumen['plantas_operando']}/{resumen['plantas_total']}\n"
            f"Líneas operando: {resumen['lineas_operando']}/{resumen['lineas_total']}\n"
            f"Alertas activas: {resumen['alertas_activas']}\n"
        )
        if plantas_falla:
            ctx += f"Plantas con problemas: {'; '.join(plantas_falla)}\n"
        if lineas_problema:
            ctx += f"Líneas con problemas: {'; '.join(lineas_problema)}\n"
        ctx += f"Top 5 generadores: {'; '.join(f'{p.nombre}={p.generacion_actual_mw:.0f}MW' for p in top_gen)}\n"
        return ctx


# === ENTRY POINT ===
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI'))
    window = PalantirCFE()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
