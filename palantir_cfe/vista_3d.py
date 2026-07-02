"""
Visor 3D Holográfico — Palantir CFE.

Renderiza un "gemelo digital" 3D estilo holográfico (como la imagen de referencia):
cuando te acercas a una estructura de CFE, la ves modelada en 3D con wireframe
brillante, rodeada de edificios de contexto y con gráficas de monitoreo industrial
en tiempo real a los lados.

Usa pyqtgraph.opengl (OpenGL) para el 3D. Si OpenGL no está disponible, muestra
un mensaje claro (no rompe el resto del dashboard).

Requiere: pyqtgraph, PyOpenGL, numpy.
"""
from __future__ import annotations

import math
import random
from collections import deque

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

import pyqtgraph as pg

from .catalogo_activos import CATALOGO, CLASES_ORDENADAS
from .datos_geograficos import PLANTAS_GENERACION, SUBESTACIONES

# Intento de importar OpenGL de pyqtgraph
try:
    import numpy as np
    import pyqtgraph.opengl as gl
    GL_DISPONIBLE = True
except Exception:
    GL_DISPONIBLE = False

# Colores holográficos
C_BG = '#050810'
C_PANEL = '#0a1420'
C_CYAN = '#00d4ff'
C_TEXT = '#8899aa'
C_TEXT_H = '#e1e8f0'
C_GREEN = '#00e676'
C_YELLOW = '#ffd600'
C_RED = '#ff1744'



class Vista3D(QWidget):
    """Widget con la escena 3D holográfica + info + gráficas en tiempo real."""

    def __init__(self):
        super().__init__()
        self.tick = 0
        self._items_estructura = []
        # Buffers de datos para las gráficas en tiempo real
        self.hist_gen = deque([0.0] * 120, maxlen=120)
        self.hist_temp = deque([0.0] * 120, maxlen=120)
        self.hist_vib = deque([0.0] * 120, maxlen=120)
        self._build_ui()

        if GL_DISPONIBLE:
            self.timer = QTimer()
            self.timer.timeout.connect(self._update_loop)
            self.timer.start(500)
            # Cargar la primera estructura
            self._cargar_estructura()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Barra superior: selector de estructura
        top = QHBoxLayout()
        lbl = QLabel("GEMELO DIGITAL 3D — ")
        lbl.setStyleSheet(f"color:{C_CYAN}; font-size:12px; font-weight:bold; letter-spacing:1px;")
        top.addWidget(lbl)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(320)
        for p in PLANTAS_GENERACION:
            self.combo.addItem(f"⚡ {p.nombre}", (p.id, "planta"))
        for s in SUBESTACIONES:
            self.combo.addItem(f"🔌 {s.nombre}", (s.id, "sub"))
        self.combo.currentIndexChanged.connect(self._cargar_estructura)
        top.addWidget(self.combo)
        top.addStretch()

        self.lbl_modo = QLabel("")
        self.lbl_modo.setStyleSheet(f"color:{C_TEXT}; font-size:10px;")
        top.addWidget(self.lbl_modo)
        lay.addLayout(top)

        # Cuerpo: 3D a la izquierda, panel de info+gráficas a la derecha
        body = QHBoxLayout()
        body.setSpacing(4)

        if GL_DISPONIBLE:
            self.vista_gl = gl.GLViewWidget()
            self.vista_gl.setBackgroundColor(QColor(C_BG))
            self.vista_gl.setCameraPosition(distance=250, elevation=25, azimuth=45)
            self.vista_gl.setMinimumWidth(550)
            self._crear_piso()
            body.addWidget(self.vista_gl, 2)
        else:
            aviso = QLabel(
                "⚠️ Vista 3D no disponible.\n\n"
                "Instala PyOpenGL para activar el gemelo digital 3D:\n"
                "    pip install PyOpenGL PyOpenGL_accelerate\n\n"
                "El resto del dashboard funciona normalmente."
            )
            aviso.setStyleSheet(f"color:{C_TEXT}; font-size:12px; padding:40px;")
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.addWidget(aviso, 2)

        # Panel derecho: info + gráficas
        body.addWidget(self._build_panel_info(), 1)
        lay.addLayout(body, 1)

    def _build_panel_info(self):
        panel = QWidget()
        panel.setMaximumWidth(360)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(4, 4, 4, 4)
        pl.setSpacing(6)

        # Tarjeta de información (estilo callout de la imagen de referencia)
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(f"""
            QLabel {{ background:{C_PANEL}; color:{C_TEXT_H}; border:1px solid {C_CYAN};
            border-radius:6px; padding:10px; font-family:'Consolas'; font-size:10px; }}
        """)
        self.lbl_info.setWordWrap(True)
        pl.addWidget(self.lbl_info)

        # Gráficas de monitoreo en tiempo real
        pg.setConfigOptions(antialias=True)
        self.plt_gen = self._mini_grafica("Generación (MW)", C_GREEN)
        self.plt_temp = self._mini_grafica("Temperatura (°C)", C_RED)
        self.plt_vib = self._mini_grafica("Vibración (mm/s)", C_YELLOW)
        for _, plt in [self.plt_gen, self.plt_temp, self.plt_vib]:
            pl.addWidget(plt)

        pl.addStretch()
        return panel

    def _mini_grafica(self, titulo, color):
        w = pg.PlotWidget()
        w.setBackground(C_PANEL)
        w.setFixedHeight(110)
        w.setTitle(titulo, color=color, size="9pt")
        w.showGrid(x=False, y=True, alpha=0.15)
        w.getAxis('left').setTextPen(C_TEXT)
        w.getAxis('bottom').setTextPen(C_TEXT)
        curva = w.plot(pen=pg.mkPen(color, width=2))
        return (curva, w)



    def _crear_piso(self):
        """Crea la rejilla holográfica del piso (estilo Tron/Palantir)."""
        grid = gl.GLGridItem()
        grid.setSize(400, 400)
        grid.setSpacing(20, 20)
        grid.setColor((0, 212, 255, 80))
        self.vista_gl.addItem(grid)
        self._grid = grid

    def _crear_contexto_ciudad(self):
        """Edificios de contexto alrededor (para dar sensación de entorno urbano)."""
        random.seed(42)  # determinista
        for _ in range(40):
            x = random.uniform(-180, 180)
            y = random.uniform(-180, 180)
            # Dejar libre el centro donde va la estructura principal
            if abs(x) < 60 and abs(y) < 60:
                continue
            w = random.uniform(8, 20)
            h = random.uniform(10, 60)
            self._agregar_caja(x, y, w, w, h, color=(0.1, 0.4, 0.7, 0.35))

    def _agregar_caja(self, cx, cy, ancho, largo, alto, color):
        """Agrega un edificio-caja wireframe a la escena."""
        hx, hy = ancho / 2, largo / 2
        base = [[cx-hx, cy-hy, 0], [cx+hx, cy-hy, 0], [cx+hx, cy+hy, 0], [cx-hx, cy+hy, 0], [cx-hx, cy-hy, 0]]
        top = [[x, y, alto] for x, y, _ in base]
        pts_base = np.array(base)
        pts_top = np.array(top)
        item_b = gl.GLLinePlotItem(pos=pts_base, color=color, width=1, antialias=True)
        item_t = gl.GLLinePlotItem(pos=pts_top, color=color, width=1, antialias=True)
        self.vista_gl.addItem(item_b)
        self.vista_gl.addItem(item_t)
        for i in range(4):
            vert = np.array([base[i], top[i]])
            iv = gl.GLLinePlotItem(pos=vert, color=color, width=1, antialias=True)
            self.vista_gl.addItem(iv)
        return [item_b, item_t]

    def _cargar_estructura(self):
        """Carga en 3D la estructura seleccionada + su contexto."""
        if not GL_DISPONIBLE:
            return
        from .modelos_3d import geometria_para_clase

        # Limpiar escena (dejar el grid)
        self.vista_gl.clear()
        self._crear_piso()
        self._crear_contexto_ciudad()
        self._items_estructura = []

        data = self.combo.currentData()
        if not data:
            return
        activo_id, tipo = data

        # Determinar la clase del activo
        clase_id, nombre, extra = self._resolver_activo(activo_id, tipo)
        self.clase_actual = clase_id
        self.nombre_actual = nombre

        # Generar y dibujar la geometría 3D holográfica
        geo = geometria_para_clase(clase_id)
        for linea in geo.lineas:
            item = gl.GLLinePlotItem(pos=linea, color=geo.color, width=2.2, antialias=True)
            item.setGLOptions('additive')  # efecto glow holográfico
            self.vista_gl.addItem(item)
            self._items_estructura.append(item)

        # Etiqueta flotante con el nombre
        try:
            txt = gl.GLTextItem(pos=(0, 0, geo.altura_m + 10),
                                text=nombre[:28], color=(0, 212, 255, 255))
            self.vista_gl.addItem(txt)
        except Exception:
            pass  # GLTextItem puede no estar en versiones viejas

        self._info_extra = extra
        self._actualizar_info()

    def _resolver_activo(self, activo_id, tipo):
        """Encuentra la clase del catálogo y datos del activo seleccionado."""
        from .datos_geograficos import TipoPlanta
        tipo_a_clase = {
            TipoPlanta.HIDROELECTRICA: "hidroelectrica", TipoPlanta.EOLICA: "eolica",
            TipoPlanta.TERMOELECTRICA: "termoelectrica", TipoPlanta.SOLAR: "solar",
            TipoPlanta.CICLO_COMBINADO: "ciclo_combinado", TipoPlanta.TURBOGAS: "termoelectrica",
            TipoPlanta.GEOTERMICA: "termoelectrica",
        }
        if tipo == "planta":
            for p in PLANTAS_GENERACION:
                if p.id == activo_id:
                    clase = tipo_a_clase.get(p.tipo, "termoelectrica")
                    if "Carbón" in p.combustible:
                        clase = "carbonifera"
                    return clase, p.nombre, {
                        "Tipo": p.tipo.value, "Estado": p.estado.value,
                        "Municipio": p.municipio, "Capacidad": f"{p.capacidad_mw} MW",
                        "Unidades": str(p.unidades), "Combustible": p.combustible,
                        "Coords": f"{p.lat:.4f}, {p.lon:.4f}",
                    }
        else:
            for s in SUBESTACIONES:
                if s.id == activo_id:
                    return "subestacion", s.nombre, {
                        "Tipo": "Subestación", "Estado": s.estado.value,
                        "Tensión": s.nivel_tension.value, "Capacidad": f"{s.capacidad_mva} MVA",
                        "Coords": f"{s.lat:.4f}, {s.lon:.4f}",
                    }
        return "termoelectrica", activo_id, {}



    def _actualizar_info(self):
        """Actualiza la tarjeta de información de la estructura."""
        clase = CATALOGO.get(getattr(self, "clase_actual", ""), None)
        icono = clase.icono if clase else "●"
        nombre = getattr(self, "nombre_actual", "—")
        extra = getattr(self, "_info_extra", {})
        lineas = [f"{icono} {nombre}", "─" * 32]
        for k, v in extra.items():
            lineas.append(f"{k:12s}: {v}")
        self.lbl_info.setText("\n".join(lineas))

    def _update_loop(self):
        """Actualiza gráficas en tiempo real y rota la cámara suavemente."""
        if not GL_DISPONIBLE:
            return
        self.tick += 1

        # Rotación automática lenta de la cámara (efecto showroom)
        try:
            self.vista_gl.orbit(0.6, 0)
        except Exception:
            pass

        # Simular telemetría de la estructura seleccionada
        base_gen = 400 + 200 * math.sin(self.tick * 0.05)
        gen = max(0, base_gen + random.gauss(0, 15))
        temp = 480 + 40 * math.sin(self.tick * 0.03) + random.gauss(0, 5)
        vib = 1.8 + 0.6 * math.sin(self.tick * 0.08) + random.gauss(0, 0.1)

        self.hist_gen.append(gen)
        self.hist_temp.append(temp)
        self.hist_vib.append(vib)

        x = list(range(len(self.hist_gen)))
        self.plt_gen[0].setData(x, list(self.hist_gen))
        self.plt_temp[0].setData(x, list(self.hist_temp))
        self.plt_vib[0].setData(x, list(self.hist_vib))

        # Efecto de "pulso" holográfico en la estructura (variar el ancho)
        pulso = 2.0 + 0.6 * abs(math.sin(self.tick * 0.15))
        for item in self._items_estructura:
            try:
                item.setData(width=pulso)
            except Exception:
                pass

    def actualizar_telemetria_externa(self, gen_mw: float, temp_c: float, vib: float):
        """Permite alimentar datos reales desde el dashboard (opcional)."""
        self.hist_gen.append(gen_mw)
        self.hist_temp.append(temp_c)
        self.hist_vib.append(vib)
