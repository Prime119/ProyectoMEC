"""
Mapa OSINT geográfico — Palantir CFE.

Mapa oscuro de mundo real (estilo Palantir / ShadowBroker OSINT) construido con
Leaflet dentro de un QWebEngineView. Muestra toda la infraestructura de CFE del
Noroeste como marcadores temáticos sobre un basemap oscuro real, con:

- Basemap oscuro (CartoDB dark_matter) + capa satelital opcional (Esri)
- Marcadores por tipo de activo (color e ícono según categoría)
- Estado operativo en tiempo real (verde/amarillo/rojo)
- Líneas de transmisión dibujadas y coloreadas por carga
- Filtros por capa (encender/apagar cada categoría, como en OSINT)
- Buscador "LOCALIZAR" para saltar a cualquier activo
- Herramienta de medición de distancia
- Popups con telemetría al hacer clic
- Puente Python<->JS: al clic en un marcador se emite una señal (para abrir el 3D)

Requiere: PyQt6-WebEngine e internet (para las teselas y Leaflet).
Si WebEngine no está disponible, el dashboard usa el mapa pyqtgraph como respaldo.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QObject, pyqtSlot, QUrl

# Verificar disponibilidad de WebEngine
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    WEBENGINE_DISPONIBLE = True
except Exception:
    WEBENGINE_DISPONIBLE = False
    QWidget = object  # type: ignore

from .datos_geograficos import (
    PLANTAS_GENERACION, SUBESTACIONES, LINEAS_TRANSMISION,
    TipoPlanta, NivelTension,
)
from .catalogo_activos import CATALOGO



# Mapeo de tipo de planta -> clase del catálogo (para color e ícono)
_TIPO_A_CLASE = {
    TipoPlanta.HIDROELECTRICA: "hidroelectrica",
    TipoPlanta.EOLICA: "eolica",
    TipoPlanta.TERMOELECTRICA: "termoelectrica",
    TipoPlanta.SOLAR: "solar",
    TipoPlanta.CICLO_COMBINADO: "ciclo_combinado",
    TipoPlanta.TURBOGAS: "termoelectrica",
    TipoPlanta.GEOTERMICA: "termoelectrica",
}


def _clase_de_planta(p) -> str:
    if "Carbón" in p.combustible:
        return "carbonifera"
    return _TIPO_A_CLASE.get(p.tipo, "termoelectrica")


def _activos_iniciales() -> list[dict]:
    """Construye la lista de activos (plantas + subestaciones) para el mapa."""
    activos = []
    for p in PLANTAS_GENERACION:
        clase = _clase_de_planta(p)
        info = CATALOGO.get(clase)
        activos.append({
            "id": p.id, "nombre": p.nombre, "lat": p.lat, "lon": p.lon,
            "categoria": info.categoria.value if info else "Generación",
            "clase": clase, "icono": info.icono if info else "⚡",
            "color": info.color if info else "#00d4ff",
            "detalle": f"{p.tipo.value} · {p.capacidad_mw} MW · {p.municipio}, {p.estado.value}",
        })
    for s in SUBESTACIONES:
        info = CATALOGO.get("subestacion")
        activos.append({
            "id": s.id, "nombre": s.nombre, "lat": s.lat, "lon": s.lon,
            "categoria": "Transmisión", "clase": "subestacion",
            "icono": "⚡", "color": info.color if info else "#00d4ff",
            "detalle": f"Subestación · {s.nivel_tension.value} · {s.capacidad_mva} MVA · {s.estado.value}",
        })
    return activos


def _lineas_iniciales() -> list[dict]:
    """Construye las líneas de transmisión (polilíneas) para el mapa."""
    def coords(node_id):
        for s in SUBESTACIONES:
            if s.id == node_id:
                return [s.lat, s.lon]
        for p in PLANTAS_GENERACION:
            if p.id == node_id:
                return [p.lat, p.lon]
        return None

    lineas = []
    for lt in LINEAS_TRANSMISION:
        o = coords(lt.origen_id)
        d = coords(lt.destino_id)
        if o and d:
            lineas.append({
                "id": lt.id, "nombre": lt.nombre,
                "coords": [o, d],
                "tension": lt.nivel_tension.value,
                "es_400": lt.nivel_tension == NivelTension.KV_400,
            })
    return lineas



class _Puente(QObject):
    """Puente JS -> Python: recibe eventos del mapa (clic en marcador)."""
    activoSeleccionado = pyqtSignal(str)  # emite el id del activo

    @pyqtSlot(str)
    def seleccionar(self, activo_id: str):
        self.activoSeleccionado.emit(activo_id)


class MapaOSINT(QWidget):
    """Mapa geográfico OSINT con Leaflet dentro de un QWebEngineView."""

    activoSeleccionado = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._listo = False
        self._pendiente = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.view = QWebEngineView()
        lay.addWidget(self.view)

        # Puente JS <-> Python
        self.puente = _Puente()
        self.puente.activoSeleccionado.connect(self.activoSeleccionado.emit)
        self.canal = QWebChannel()
        self.canal.registerObject("puente", self.puente)
        self.view.page().setWebChannel(self.canal)

        self.view.loadFinished.connect(self._on_load)

        # Escribir HTML a archivo y cargarlo
        html = _generar_html(_activos_iniciales(), _lineas_iniciales())
        self._archivo = Path(__file__).resolve().parent / "_mapa_osint.html"
        self._archivo.write_text(html, encoding="utf-8")
        self.view.load(QUrl.fromLocalFile(str(self._archivo)))

    def _on_load(self, ok: bool):
        self._listo = ok
        if ok and self._pendiente is not None:
            self.actualizar_estados(*self._pendiente)
            self._pendiente = None

    def actualizar_estados(self, estados_activos: dict, estados_lineas: dict):
        """
        Actualiza colores/estado en tiempo real.
        estados_activos: {id: {"estado": "Operando"|"Falla"|..., "info": "texto"}}
        estados_lineas:  {id: {"carga": 0-100, "estado": "..."}}
        """
        if not self._listo:
            self._pendiente = (estados_activos, estados_lineas)
            return
        payload = json.dumps({"activos": estados_activos, "lineas": estados_lineas})
        self.view.page().runJavaScript(f"actualizarEstados({payload});")

    def localizar(self, nombre: str):
        """Centra el mapa en un activo por nombre."""
        if self._listo:
            self.view.page().runJavaScript(f"buscarActivo({json.dumps(nombre)});")



def _generar_html(activos: list[dict], lineas: list[dict]) -> str:
    """Genera el HTML completo del mapa Leaflet con los datos inyectados."""
    return (_HTML_TEMPLATE
            .replace("__ACTIVOS__", json.dumps(activos, ensure_ascii=False))
            .replace("__LINEAS__", json.dumps(lineas, ensure_ascii=False)))


# =============================================================================
# PLANTILLA HTML/JS (Leaflet + basemap oscuro estilo OSINT)
# =============================================================================

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html,body,#map{height:100%;margin:0;background:#05080f;}
  .leaflet-container{background:#05080f;font-family:'Segoe UI',sans-serif;}
  .panel{position:absolute;z-index:1000;background:rgba(10,20,32,.92);
    border:1px solid #1a2a3a;border-radius:6px;color:#cfe3f5;font-size:12px;
    padding:8px 10px;backdrop-filter:blur(4px);}
  #buscador{top:10px;left:10px;display:flex;gap:6px;align-items:center;}
  #buscador input{background:#0d1520;border:1px solid #00d4ff;color:#e1e8f0;
    padding:6px 8px;border-radius:4px;font-size:12px;width:220px;outline:none;}
  #buscador button{background:#00d4ff;color:#000;border:none;padding:6px 12px;
    border-radius:4px;font-weight:bold;cursor:pointer;}
  #btnMedir{background:#0d1520;border:1px solid #00d4ff;color:#00d4ff;
    padding:6px 10px;border-radius:4px;cursor:pointer;}
  #btnMedir.activo{background:#00d4ff;color:#000;}
  #leyenda{bottom:16px;left:10px;max-width:230px;line-height:1.7;}
  #leyenda b{color:#00d4ff;}
  .punto{display:inline-block;width:10px;height:10px;border-radius:50%;
    margin-right:6px;vertical-align:middle;}
  .lp{color:#8fb3d0;}
  .popup-t{color:#00d4ff;font-weight:bold;font-size:13px;}
  .popup-d{color:#cfe3f5;font-size:11px;}
  .estado-ok{color:#00e676;} .estado-warn{color:#ffd600;} .estado-bad{color:#ff1744;}
  @keyframes pulso{0%{opacity:1;}50%{opacity:.35;}100%{opacity:1;}}
</style>
</head>
<body>
<div id="map"></div>
<div id="buscador" class="panel">
  <input id="txtBuscar" placeholder="LOCALIZAR activo CFE..." />
  <button onclick="buscarDesdeInput()">🔍</button>
  <button id="btnMedir" onclick="toggleMedir()">📏 Medir</button>
</div>
<div id="leyenda" class="panel"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
"""


_HTML_TEMPLATE += r"""
var ACTIVOS = __ACTIVOS__;
var LINEAS  = __LINEAS__;

// Basemaps oscuros (estilo OSINT)
var oscuro = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {attribution:'CARTO · OpenStreetMap', subdomains:'abcd', maxZoom:19});
var satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {attribution:'Esri', maxZoom:19});

var map = L.map('map', {center:[28.5,-111.0], zoom:6, layers:[oscuro], zoomControl:true});

// Grupos por categoría (capas conmutables tipo OSINT)
var grupos = {};
var markers = {};   // id -> marker
var lineItems = {}; // id -> polyline

function radioPorCategoria(cat){
  if(cat==='Generación') return 8;
  if(cat==='Transmisión') return 6;
  return 5;
}

// Crear marcadores de activos
ACTIVOS.forEach(function(a){
  if(!grupos[a.categoria]) grupos[a.categoria] = L.layerGroup().addTo(map);
  var m = L.circleMarker([a.lat,a.lon],{
    radius:radioPorCategoria(a.categoria), color:a.color, weight:2,
    fillColor:a.color, fillOpacity:0.55
  });
  m._base = a;
  m.bindPopup(popupHTML(a,'Operando'));
  m.on('click', function(){
    if(window.puente) window.puente.seleccionar(a.id);
  });
  m.addTo(grupos[a.categoria]);
  markers[a.id] = m;
});

// Dibujar líneas de transmisión
if(!grupos['Líneas']) grupos['Líneas'] = L.layerGroup().addTo(map);
LINEAS.forEach(function(l){
  var color = l.es_400 ? '#00e676' : '#00d4ff';
  var pl = L.polyline(l.coords,{color:color,weight:l.es_400?3:2,opacity:0.7});
  pl.bindPopup('<span class="popup-t">'+l.nombre+'</span><br><span class="popup-d">'+l.tension+'</span>');
  pl._base = l;
  pl.addTo(grupos['Líneas']);
  lineItems[l.id] = pl;
});

// Control de capas (basemaps + filtros por categoría)
L.control.layers(
  {'🌑 Oscuro':oscuro, '🛰️ Satélite':satelite},
  grupos, {collapsed:false, position:'topright'}
).addTo(map);

function popupHTML(a, estado){
  var cls = estado==='Falla'?'estado-bad':(estado==='Mantenimiento'||estado==='Arranque'?'estado-warn':'estado-ok');
  return '<span class="popup-t">'+a.icono+' '+a.nombre+'</span><br>'+
         '<span class="popup-d">'+a.detalle+'</span><br>'+
         '<span class="'+cls+'">● '+estado+'</span><br>'+
         '<span class="lp" style="font-size:10px">'+a.lat.toFixed(4)+', '+a.lon.toFixed(4)+'</span>';
}
"""


_HTML_TEMPLATE += r"""
// Actualización de estados en tiempo real (desde Python)
function actualizarEstados(data){
  var A = data.activos || {};
  Object.keys(A).forEach(function(id){
    var m = markers[id]; if(!m) return;
    var est = A[id].estado || 'Operando';
    var col;
    if(est==='Falla') col='#ff1744';
    else if(est==='Mantenimiento'||est==='Arranque') col='#ffd600';
    else col = m._base.color;
    m.setStyle({color:col, fillColor:col});
    // Radio según generación relativa (si viene)
    if(A[id].escala){ m.setRadius(6 + 8*A[id].escala); }
    m.setPopupContent(popupHTML(m._base, est) +
      (A[id].info?('<br><span class="popup-d">'+A[id].info+'</span>'):''));
    if(est==='Falla'){ if(m._path) m._path.style.animation='pulso 1s infinite'; }
    else { if(m._path) m._path.style.animation=''; }
  });
  var L2 = data.lineas || {};
  Object.keys(L2).forEach(function(id){
    var pl = lineItems[id]; if(!pl) return;
    var carga = L2[id].carga || 0;
    var est = L2[id].estado || 'Operando';
    var col;
    if(est==='Falla') col='#ff1744';
    else if(carga>85) col='#ff9100';
    else if(carga>70) col='#ffd600';
    else col = pl._base.es_400 ? '#00e676':'#00d4ff';
    pl.setStyle({color:col});
    pl.setPopupContent('<span class="popup-t">'+pl._base.nombre+'</span><br>'+
      '<span class="popup-d">'+pl._base.tension+' · carga '+carga.toFixed(0)+'%</span>');
  });
}

// Buscador "LOCALIZAR"
function buscarActivo(nombre){
  var q = (nombre||'').toLowerCase();
  for(var id in markers){
    if(markers[id]._base.nombre.toLowerCase().indexOf(q)>=0){
      var m = markers[id];
      map.flyTo(m.getLatLng(), 13, {duration:1.2});
      m.openPopup();
      return true;
    }
  }
  return false;
}
function buscarDesdeInput(){ buscarActivo(document.getElementById('txtBuscar').value); }
document.getElementById('txtBuscar').addEventListener('keydown',function(e){
  if(e.key==='Enter') buscarDesdeInput();
});
"""


_HTML_TEMPLATE += r"""
// Herramienta de medición de distancia
var medir=false, ptosMedir=[], lineaMedir=null;
function toggleMedir(){
  medir=!medir;
  document.getElementById('btnMedir').classList.toggle('activo',medir);
  ptosMedir=[];
  if(lineaMedir){map.removeLayer(lineaMedir);lineaMedir=null;}
  map.getContainer().style.cursor = medir?'crosshair':'';
}
function haversine(a,b){
  var R=6371,dLat=(b[0]-a[0])*Math.PI/180,dLon=(b[1]-a[1])*Math.PI/180;
  var s=Math.sin(dLat/2)*Math.sin(dLat/2)+Math.cos(a[0]*Math.PI/180)*
    Math.cos(b[0]*Math.PI/180)*Math.sin(dLon/2)*Math.sin(dLon/2);
  return R*2*Math.atan2(Math.sqrt(s),Math.sqrt(1-s));
}
map.on('click',function(e){
  if(!medir) return;
  ptosMedir.push([e.latlng.lat,e.latlng.lng]);
  if(ptosMedir.length===2){
    if(lineaMedir) map.removeLayer(lineaMedir);
    lineaMedir=L.polyline(ptosMedir,{color:'#00d4ff',dashArray:'6',weight:2}).addTo(map);
    var d=haversine(ptosMedir[0],ptosMedir[1]);
    lineaMedir.bindPopup('📏 '+d.toFixed(1)+' km').openPopup();
    ptosMedir=[];
  }
});

// Leyenda por categoría
(function(){
  var cats={};
  ACTIVOS.forEach(function(a){ if(!cats[a.categoria]) cats[a.categoria]=a.color; });
  var html='<b>INFRAESTRUCTURA CFE</b><br>';
  Object.keys(cats).forEach(function(c){
    html+='<span class="punto" style="background:'+cats[c]+'"></span>'+c+'<br>';
  });
  html+='<span class="punto" style="background:#00e676"></span>Línea 400kV<br>';
  html+='<span class="punto" style="background:#00d4ff"></span>Línea 230kV';
  document.getElementById('leyenda').innerHTML=html;
})();

// Puente Python <-> JS
new QWebChannel(qt.webChannelTransport, function(channel){
  window.puente = channel.objects.puente;
});
"""


_HTML_TEMPLATE += r"""
</script>
</body>
</html>
"""
