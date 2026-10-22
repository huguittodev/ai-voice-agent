"""Diagnóstico del hardware y subsistema de audio para captura y reproducción."""

import json
import os
import shutil
import subprocess
import sys


def _check_is_wsl() -> bool:
    if not os.path.exists("/proc/version"):
        return False
    with open("/proc/version", encoding="utf-8") as f:
        return "microsoft" in f.read().lower()


def inspect_audio_devices():
    diagnostic = {
        "platform": sys.platform,
        "is_wsl": _check_is_wsl(),
        "env_vars": {
            "PULSE_SERVER": os.environ.get("PULSE_SERVER"),
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY"),
            "DISPLAY": os.environ.get("DISPLAY"),
            "WSL_DISTRO_NAME": os.environ.get("WSL_DISTRO_NAME"),
        },
        "dev_snd_exists": os.path.exists("/dev/snd"),
        "dev_snd_nodes": os.listdir("/dev/snd") if os.path.exists("/dev/snd") else [],
        "cli_tools": {},
        "alsa_devices": {
            "playback": [],
            "capture": [],
        },
        "portaudio_available": False,
        "sounddevice_devices": [],
        "default_input_device": None,
        "default_output_device": None,
    }

    # Comprobar herramientas CLI
    for tool in ["arecord", "aplay", "pactl", "pw-record", "ffmpeg"]:
        path = shutil.which(tool)
        diagnostic["cli_tools"][tool] = path

    # Comprobar arecord -l
    if diagnostic["cli_tools"]["arecord"]:
        try:
            out = subprocess.check_output(["arecord", "-l"], text=True, stderr=subprocess.STDOUT, timeout=2)
            diagnostic["alsa_devices"]["capture"] = out.strip().split("\n")
        except (subprocess.SubprocessError, OSError) as e:
            diagnostic["alsa_devices"]["capture"] = [f"Error ejecutando arecord -l: {e}"]

    # Comprobar aplay -l
    if diagnostic["cli_tools"]["aplay"]:
        try:
            out = subprocess.check_output(["aplay", "-l"], text=True, stderr=subprocess.STDOUT, timeout=2)
            diagnostic["alsa_devices"]["playback"] = out.strip().split("\n")
        except (subprocess.SubprocessError, OSError) as e:
            diagnostic["alsa_devices"]["playback"] = [f"Error ejecutando aplay -l: {e}"]

    # Comprobar sounddevice si está instalado
    try:
        import sounddevice as sd  # type: ignore
        diagnostic["portaudio_available"] = True
        devices = sd.query_devices()
        diagnostic["sounddevice_devices"] = [dict(d) for d in devices]
        default_in, default_out = sd.default.device
        diagnostic["default_input_device"] = default_in
        diagnostic["default_output_device"] = default_out
    except ImportError:
        diagnostic["sounddevice_error"] = "Librería sounddevice no instalada en el venv."
    except (RuntimeError, OSError) as e:
        diagnostic["sounddevice_error"] = f"Error consultando sounddevice: {e}"

    print("=== DIAGNÓSTICO DE AUDIO ===", flush=True)
    print(f"WSL2 Detectado: {diagnostic['is_wsl']}", flush=True)
    print(f"PULSE_SERVER: {diagnostic['env_vars']['PULSE_SERVER']}", flush=True)
    print(f"/dev/snd existe: {diagnostic['dev_snd_exists']} (nodos: {len(diagnostic['dev_snd_nodes'])})", flush=True)
    print(f"Herramientas CLI: {diagnostic['cli_tools']}", flush=True)
    print(f"Captura ALSA (arecord): {diagnostic['alsa_devices']['capture']}", flush=True)
    print(f"Reproducción ALSA (aplay): {diagnostic['alsa_devices']['playback']}", flush=True)
    if "sounddevice_error" in diagnostic:
        print(f"sounddevice: {diagnostic['sounddevice_error']}", flush=True)
    else:
        print(f"sounddevice dispositivos detectados: {len(diagnostic['sounddevice_devices'])}", flush=True)
        print(f"Entrada por defecto: {diagnostic['default_input_device']} | Salida: {diagnostic['default_output_device']}", flush=True)
    print("=============================", flush=True)

    out_json = "output/audio_env_diagnostic.json"
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(diagnostic, f, ensure_ascii=False, indent=2)

    return diagnostic


if __name__ == "__main__":
    inspect_audio_devices()
