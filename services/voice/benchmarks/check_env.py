"""Diagnóstico del entorno y compatibilidad paso a paso con flush inmediato."""

import sys

print("[1/6] Iniciando script de diagnóstico...", flush=True)

import psutil

print(f"[2/6] psutil cargado. Python: {sys.version.split()[0]}", flush=True)

ram = psutil.virtual_memory()
print(
    f"      RAM Total: {ram.total / (1024**3):.2f} GB | Disp: {ram.available / (1024**3):.2f} GB",
    flush=True,
)

print("[3/6] Importando soundfile...", flush=True)
import soundfile

print(f"      soundfile versión: {soundfile.__version__}", flush=True)

print("[4/6] Importando piper-tts...", flush=True)
print("      piper-tts cargado correctamente", flush=True)

print("[5/6] Importando ctranslate2...", flush=True)
import ctranslate2

print(f"      CTranslate2 versión: {ctranslate2.__version__}", flush=True)

print("[6/6] Verificando soporte CPU y CUDA...", flush=True)
supported_cpu = ctranslate2.get_supported_compute_types("cpu")
print(f"      Tipos soportados en CPU: {supported_cpu}", flush=True)

print("      Comprobando CUDA device count...", flush=True)
try:
    cuda_count = ctranslate2.get_cuda_device_count()
    print(f"      Dispositivos CUDA en CTranslate2: {cuda_count}", flush=True)
    if cuda_count > 0:
        supported_cuda = ctranslate2.get_supported_compute_types("cuda")
        print(f"      Tipos soportados en CUDA: {supported_cuda}", flush=True)
except Exception as e:
    print(f"      Aviso/Error comprobando CUDA: {e}", flush=True)

print("=== DIAGNÓSTICO COMPLETADO EXITOSAMENTE ===", flush=True)
