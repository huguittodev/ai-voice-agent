"""Descarga verificada de modelos de voz para Piper TTS."""

import os
import sys
import urllib.request

MODELS = {
    "davefx": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json",
        "dir_name": "es_ES-davefx-medium",
        "model_file": "es_ES-davefx-medium.onnx",
        "config_file": "es_ES-davefx-medium.onnx.json",
        "expected_min_bytes": 60 * 1024 * 1024,  # ~63 MB
        "license": "CC0 1.0 Universal (Public Domain)",
        "source": "https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium",
    },
    "sharvard": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx.json",
        "dir_name": "es_ES-sharvard-medium",
        "model_file": "es_ES-sharvard-medium.onnx",
        "config_file": "es_ES-sharvard-medium.onnx.json",
        "expected_min_bytes": 70 * 1024 * 1024,  # ~76 MB
        "license": "MIT",
        "source": "https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/sharvard/medium",
    },
}


def download_file(url: str, dest_path: str):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        print(
            f"  [OK] Ya existe: {dest_path} ({os.path.getsize(dest_path) / (1024 * 1024):.2f} MB)",
            flush=True,
        )
        return
    print(f"  Descargando: {url} -> {dest_path}", flush=True)
    temp_path = dest_path + ".tmp"
    urllib.request.urlretrieve(url, temp_path)
    os.rename(temp_path, dest_path)
    print(
        f"  [COMPLETADO] {dest_path} ({os.path.getsize(dest_path) / (1024 * 1024):.2f} MB)",
        flush=True,
    )


def download_voice(voice_key: str = "davefx", base_dir: str = "models/piper") -> dict:
    if voice_key not in MODELS:
        raise ValueError(
            f"Voz desconocida: {voice_key}. Opciones: {list(MODELS.keys())}"
        )

    meta = MODELS[voice_key]
    target_dir = os.path.join(base_dir, meta["dir_name"])
    os.makedirs(target_dir, exist_ok=True)

    onnx_path = os.path.join(target_dir, meta["model_file"])
    json_path = os.path.join(target_dir, meta["config_file"])

    print(f"Verificando / descargando voz '{voice_key}' en {target_dir}...", flush=True)
    download_file(meta["json_url"], json_path)
    download_file(meta["onnx_url"], onnx_path)

    actual_size = os.path.getsize(onnx_path)
    if actual_size < meta["expected_min_bytes"]:
        raise RuntimeError(
            f"El archivo descargado {onnx_path} es menor al esperado: {actual_size} bytes"
        )

    print(f"Voz '{voice_key}' lista para usar. Licencia: {meta['license']}", flush=True)
    return {
        "model_path": onnx_path,
        "config_path": json_path,
        "license": meta["license"],
        "source": meta["source"],
        "size_bytes": actual_size,
    }


if __name__ == "__main__":
    voice_to_download = sys.argv[1] if len(sys.argv) > 1 else "davefx"
    download_voice(voice_to_download)
