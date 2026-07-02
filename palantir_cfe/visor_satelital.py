"""
Visor Satelital con Detección IA — Palantir CFE.

Widget PyQt6 que muestra imágenes satelitales con overlay de las detecciones
de infraestructura de CFE. Permite:
- Seleccionar una planta/subestación conocida y ver su imagen satelital
- Ejecutar el análisis de IA y ver las detecciones dibujadas
- Ver las coordenadas exactas de cada activo detectado
- Filtrar por clase de activo
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QFrame, QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush, QFont

from .datos_geograficos import PLANTAS_GENERACION, SUBESTACIONES
from .satelite import ClienteSatelital, AreaSatelital
from .deteccion_ia import MotorDeteccion, Deteccion



# Colores (consistentes con el dashboard)
C_BG = '#0a0e17'
C_PANEL = '#0f1520'
C_BORDER = '#1a2332'
C_TEXT = '#8899aa'
C_TEXT_H = '#e1e8f0'
C_ACCENT = '#00d4ff'
C_GREEN = '#00e676'
C_RED = '#ff1744'
C_PURPLE = '#aa00ff'


class VisorSatelital(QWidget):
    """Widget principal del visor satelital con detección IA."""

    def __init__(self, modelo_onnx: str | None = None):
        super().__init__()
        self.cliente = ClienteSatelital(proveedor="esri")
        self.motor = MotorDeteccion(modelo_onnx=modelo_onnx)
        self.area_actual: Optional[AreaSatelital] = None
        self.detecciones: list[Deteccion] = []
        self._analizando = False
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Barra de control
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)

        lbl = QLabel("UBICACIÓN:")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:10px; font-weight:bold;")
        ctrl.addWidget(lbl)

        # Selector de ubicación (todas las plantas y subestaciones)
        self.combo_ubicacion = QComboBox()
        self.combo_ubicacion.setMinimumWidth(280)
        for p in PLANTAS_GENERACION:
            self.combo_ubicacion.addItem(f"⚡ {p.nombre}", (p.lon, p.lat))
        for s in SUBESTACIONES:
            self.combo_ubicacion.addItem(f"🔌 {s.nombre}", (s.lon, s.lat))
        ctrl.addWidget(self.combo_ubicacion)

        lbl_z = QLabel("ZOOM:")
        lbl_z.setStyleSheet(f"color:{C_TEXT}; font-size:10px; font-weight:bold;")
        ctrl.addWidget(lbl_z)
        self.spin_zoom = QSpinBox()
        self.spin_zoom.setRange(12, 19)
        self.spin_zoom.setValue(17)
        self.spin_zoom.setFixedWidth(50)
        ctrl.addWidget(self.spin_zoom)

        self.btn_cargar = QPushButton("🛰️ CARGAR IMAGEN")
        self.btn_cargar.setStyleSheet(f"background:{C_ACCENT}; color:#000; font-weight:bold; padding:6px 12px; border:none; border-radius:3px;")
        self.btn_cargar.clicked.connect(self._cargar_imagen)
        ctrl.addWidget(self.btn_cargar)

        self.btn_analizar = QPushButton("🤖 DETECTAR CON IA")
        self.btn_analizar.setStyleSheet(f"background:{C_PURPLE}; color:#fff; font-weight:bold; padding:6px 12px; border:none; border-radius:3px;")
        self.btn_analizar.clicked.connect(self._analizar)
        ctrl.addWidget(self.btn_analizar)

        ctrl.addStretch()
        self.lbl_modo = QLabel(f"Modo IA: {self.motor.modo}")
        self.lbl_modo.setStyleSheet(f"color:{C_PURPLE}; font-size:10px; font-weight:bold;")
        ctrl.addWidget(self.lbl_modo)
        lay.addLayout(ctrl)

        # Split: imagen a la izquierda, tabla de detecciones a la derecha
        body = QHBoxLayout()
        body.setSpacing(4)

        # Vista de la imagen satelital
        self.escena = QGraphicsScene()
        self.vista = QGraphicsView(self.escena)
        self.vista.setStyleSheet(f"background:{C_BG}; border:1px solid {C_BORDER};")
        self.vista.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.vista.setMinimumWidth(500)
        body.addWidget(self.vista, 2)

        # Panel de detecciones
        panel = QWidget()
        panel.setMaximumWidth(320)
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(2, 2, 2, 2)
        panel_lay.setSpacing(4)

        self.lbl_estado = QLabel("Selecciona una ubicación y carga la imagen.")
        self.lbl_estado.setStyleSheet(f"color:{C_TEXT}; font-size:10px;")
        self.lbl_estado.setWordWrap(True)
        panel_lay.addWidget(self.lbl_estado)

        headers = ["Activo", "Conf", "Coordenadas"]
        self.tbl_det = QTableWidget(0, len(headers))
        self.tbl_det.setHorizontalHeaderLabels(headers)
        self.tbl_det.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_det.verticalHeader().setVisible(False)
        self.tbl_det.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_det.setStyleSheet(f"""
            QTableWidget {{ background:{C_PANEL}; color:{C_TEXT_H}; gridline-color:{C_BORDER};
            font-family:'Consolas'; font-size:9px; border:1px solid {C_BORDER}; }}
            QHeaderView::section {{ background:#141e2d; color:{C_ACCENT}; font-size:9px;
            font-weight:bold; padding:3px; border:none; }}
        """)
        panel_lay.addWidget(self.tbl_det, 1)

        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setStyleSheet(f"color:{C_GREEN}; font-size:9px; font-family:'Consolas';")
        self.lbl_resumen.setWordWrap(True)
        panel_lay.addWidget(self.lbl_resumen)

        body.addWidget(panel)
        lay.addLayout(body, 1)



    def _cargar_imagen(self):
        """Descarga la imagen satelital de la ubicación seleccionada."""
        lon, lat = self.combo_ubicacion.currentData()
        zoom = self.spin_zoom.value()
        self.lbl_estado.setText("🛰️ Descargando imagen satelital... (puede tardar unos segundos)")
        self.btn_cargar.setEnabled(False)

        def worker():
            try:
                area = self.cliente.area_alrededor(lon, lat, radio_m=600, zoom=zoom)
                QTimer.singleShot(0, lambda: self._on_imagen_cargada(area))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._on_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_imagen_cargada(self, area: AreaSatelital):
        self.area_actual = area
        self.detecciones = []
        self.btn_cargar.setEnabled(True)
        self._render()
        if area.imagen is None:
            self.lbl_estado.setText(
                "⚠️ No se pudo componer la imagen. Instala Pillow y httpx:\n"
                "pip install pillow httpx")
        else:
            self.lbl_estado.setText(
                f"✅ Imagen cargada ({area.ancho_px}x{area.alto_px}px, "
                f"{area.metros_por_pixel():.2f} m/px). Presiona 'DETECTAR CON IA'.")

    def _on_error(self, msg: str):
        self.btn_cargar.setEnabled(True)
        self.lbl_estado.setText(f"❌ Error: {msg}")

    def _analizar(self):
        """Ejecuta el análisis de detección IA sobre la imagen actual."""
        if self.area_actual is None:
            self.lbl_estado.setText("⚠️ Primero carga una imagen satelital.")
            return
        if self._analizando:
            return
        self._analizando = True
        self.lbl_estado.setText("🤖 Analizando con IA...")
        self.btn_analizar.setEnabled(False)

        def worker():
            dets = self.motor.analizar(self.area_actual)
            QTimer.singleShot(0, lambda: self._on_analisis_completo(dets))

        threading.Thread(target=worker, daemon=True).start()

    def _on_analisis_completo(self, detecciones: list[Deteccion]):
        self.detecciones = detecciones
        self._analizando = False
        self.btn_analizar.setEnabled(True)
        self._render()
        self._llenar_tabla()
        resumen = self.motor.resumen_detecciones(detecciones)
        texto = " | ".join(f"{k}: {v}" for k, v in resumen.items())
        self.lbl_resumen.setText(f"Total: {len(detecciones)} activos detectados\n{texto}")
        self.lbl_estado.setText(f"✅ {len(detecciones)} activos detectados y geolocalizados.")

    def _llenar_tabla(self):
        self.tbl_det.setRowCount(len(self.detecciones))
        for r, d in enumerate(self.detecciones):
            items = [
                (f"{d.icono} {d.nombre_clase}", d.color),
                (f"{d.confianza*100:.0f}%", C_GREEN if d.confianza > 0.8 else C_TEXT),
                (f"{d.lat:.5f}, {d.lon:.5f}", C_TEXT_H),
            ]
            for c, (text, color) in enumerate(items):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                if c == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_det.setItem(r, c, item)
            self.tbl_det.setRowHeight(r, 20)



    def _render(self):
        """Dibuja la imagen satelital + overlay de detecciones."""
        self.escena.clear()
        area = self.area_actual
        if area is None:
            return

        # Dibujar la imagen satelital
        if area.imagen is not None:
            pixmap = self._pil_a_pixmap(area.imagen)
            if pixmap:
                self.escena.addItem(QGraphicsPixmapItem(pixmap))
                self.escena.setSceneRect(QRectF(0, 0, pixmap.width(), pixmap.height()))
        else:
            # Placeholder si no hay imagen (sin PIL/red)
            self.escena.addRect(0, 0, area.ancho_px, area.alto_px,
                                QPen(QColor(C_BORDER)), QBrush(QColor(C_BG)))
            txt = self.escena.addText("Imagen satelital no disponible\n(instala pillow + httpx)")
            txt.setDefaultTextColor(QColor(C_TEXT))
            self.escena.setSceneRect(QRectF(0, 0, area.ancho_px, area.alto_px))

        # Dibujar detecciones
        for d in self.detecciones:
            x1, y1, x2, y2 = d.bbox_px
            color = QColor(d.color)
            pen = QPen(color, 2)
            self.escena.addRect(x1, y1, x2 - x1, y2 - y1, pen)
            # Etiqueta
            etiqueta = self.escena.addText(f"{d.icono}{d.confianza*100:.0f}%")
            etiqueta.setDefaultTextColor(color)
            f = QFont('Segoe UI', 7, QFont.Weight.Bold)
            etiqueta.setFont(f)
            etiqueta.setPos(x1, y1 - 14)

        # Ajustar vista
        self.vista.fitInView(self.escena.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    @staticmethod
    def _pil_a_pixmap(pil_img) -> Optional[QPixmap]:
        """Convierte una imagen PIL a QPixmap."""
        try:
            img = pil_img.convert("RGB")
            data = img.tobytes("raw", "RGB")
            qimg = QImage(data, img.width, img.height, img.width * 3,
                          QImage.Format.Format_RGB888)
            return QPixmap.fromImage(qimg)
        except Exception as e:
            print(f"[Visor] Error convirtiendo imagen: {e}")
            return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.area_actual is not None:
            self.vista.fitInView(self.escena.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
