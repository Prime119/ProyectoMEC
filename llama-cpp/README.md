# llama-cpp/ — Motor LLM para FALCON/Astra

Este directorio contiene el servidor de inferencia LLM local (`llama-server.exe`) 
que Astra usa como cerebro.

## Configuración rápida

```bash
python llama-cpp/setup.py
```

El script:
1. Busca `llama-server.exe` en tu PC (en astra/dist/llama-cpp/ u otras rutas conocidas)
2. Si no lo encuentra, lo descarga automáticamente de GitHub Releases
3. Te ayuda a descargar un modelo .gguf compatible

## Estructura esperada

```
llama-cpp/
  llama-server.exe    ← Servidor de inferencia (se descarga automáticamente)
  *.dll               ← Dependencias del servidor
  models/
    *.gguf            ← Tu modelo (qwen2.5-coder-3b recomendado)
  setup.py            ← Script de configuración
  README.md           ← Este archivo
```

## Modelo recomendado

Para PCs con 7-8 GB RAM sin GPU:
- **Qwen2.5-Coder-3B-Instruct** (Q4_K_M) — 2.0 GB
- Rápido, bueno para respuestas técnicas de ingeniería eléctrica

## Uso manual

Si prefieres configurarlo manualmente:

```bash
# Descargar llama-server desde:
# https://github.com/ggerganov/llama.cpp/releases

# Ejecutar el servidor:
llama-server.exe -m models/tu-modelo.gguf -c 2048 --port 8080 -t 4
```

## Notas

- `falcon.py` arranca `llama-server.exe` automáticamente al iniciar
- Puerto: 8080 (API compatible con OpenAI)
- Context: 2048 tokens (suficiente para chat industrial)
- Threads: detectados automáticamente según tu CPU
- El archivo .exe y los modelos .gguf están en `.gitignore` (son muy grandes)
