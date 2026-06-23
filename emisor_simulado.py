import serial
import time
import os
import random

ARCHIVO = "panel_de_control.txt"
PLANTILLA = """# =======================================================
# 🎛️ PANEL DE CONTROL EN VIVO - MEC INDUSTRIAL PRO
# Modifica los numeros despues del signo de igual (=), 
# presiona Ctrl+S (Guardar) y mira la consola reaccionar.
# =======================================================

# --- PARAMETROS ELECTRICOS BASICOS ---
Tension_V = 127.2
Corriente_A = 18.5
Frecuencia_Hz = 60.0
Factor_Potencia = 0.88

# --- PARAMETROS MECANICOS Y CALIDAD ---
Temperatura_C = 45.0
Vibracion_mms = 1.8
THD_pct = 4.5

# --- POTENCIAS (Mueven el Triangulo) ---
Potencia_Activa_W = 2068.0
Potencia_Reactiva_VAr = 1100.0
Potencia_Aparente_VA = 2353.0

# --- SALUD GLOBAL DEL ACTIVO ---
Salud_pct = 95.0
"""

# Si el panel no existe, lo creamos con diseño bonito
if not os.path.exists(ARCHIVO):
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        f.write(PLANTILLA)

try:
    ser = serial.Serial('COM10', 115200)
    print(f"🚀 Emisor EN VIVO iniciado en COM10.")
    print(f"👉 Abre el archivo '{ARCHIVO}' en VS Code para controlar tu Consola.")

    while True:
        datos = {}
        try:
            with open(ARCHIVO, "r", encoding="utf-8") as f:
                for linea in f:
                    # Buscamos el signo '=' y evitamos comentarios '#'
                    if "=" in linea and not linea.strip().startswith("#"):
                        clave, valor = linea.split("=")
                        datos[clave.strip()] = float(valor.strip())
            
            # Empaquetamos los 11 valores en el orden exacto que la Consola espera
            payload = f"{datos.get('Tension_V',127.2)},{datos.get('Corriente_A',18.5)},{datos.get('Vibracion_mms',1.8)},{datos.get('Temperatura_C',45.0)},{datos.get('Frecuencia_Hz',60.0)},{datos.get('Factor_Potencia',0.88)},{datos.get('THD_pct',4.5)},{datos.get('Potencia_Activa_W',2068.0)},{datos.get('Potencia_Reactiva_VAr',1100.0)},{datos.get('Potencia_Aparente_VA',2353.0)},{datos.get('Salud_pct',95.0)}\n"
            
            ser.write(payload.encode('utf-8'))
        except Exception:
            pass # Ignora errores de lectura justo al momento de presionar Ctrl+S
        time.sleep(1)
except Exception as e:
    print(f"❌ Error crítico: {e}")