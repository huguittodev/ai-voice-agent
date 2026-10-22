"""Benchmark de reconocimiento de voz (STT) con faster-whisper en español."""

import json
import os
import subprocess
import time
import wave

import psutil
from faster_whisper import WhisperModel

# Referencias ground truth de las 5 frases comerciales
GROUND_TRUTH = {
    "frase_1": {
        "text": "Buenos días, le llamo de Soluciones Cloud para presentarle nuestra herramienta de automatización para equipos comerciales.",
        "category": "Saludo y propuesta comercial",
        "keywords": [
            "Buenos días",
            "Soluciones Cloud",
            "automatización",
            "comerciales",
        ],
    },
    "frase_2": {
        "text": "Hemos ayudado a más de 150 empresas del sector a reducir un 35% sus costes operativos durante el primer trimestre de 2026.",
        "category": "Cifras, porcentajes y fechas",
        "keywords": ["150", "35%", "costes", "2026"],
    },
    "frase_3": {
        "text": "Nuestra solución se integra de forma nativa con Salesforce, HubSpot y Microsoft Dynamics mediante APIs seguras.",
        "category": "Marcas y anglicismos tecnológicos",
        "keywords": ["Salesforce", "HubSpot", "Microsoft Dynamics", "APIs"],
    },
    "frase_4": {
        "text": "Entiendo perfectamente que ahora mismo no tengan presupuesto; ¿le parece si lo comentamos brevemente el próximo jueves a las 11:30?",
        "category": "Objeción y agendamiento de reunión",
        "keywords": ["presupuesto", "jueves", "11:30"],
    },
    "frase_5": {
        "text": "Implementamos arquitecturas híbridas optimizadas sobre microservicios con cifrado de extremo a extremo sin interrumpir su operativa.",
        "category": "Complejidad técnica y fonética",
        "keywords": ["arquitecturas", "híbridas", "microservicios", "cifrado"],
    },
}


def get_vram_usage_mb() -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,nounits,noheader"],
            text=True,
            timeout=2,
        )
        return float(out.strip().split("\n")[0])
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, IndexError, OSError):
        return 0.0


def run_stt_benchmark_for_config(
    model_name: str, device: str, compute_type: str, audio_dir: str = "output/audio"
) -> dict:
    process = psutil.Process()
    ram_before_mb = process.memory_info().rss / (1024 * 1024)
    vram_before_mb = get_vram_usage_mb() if device == "cuda" else 0.0

    print(
        f"\n--- Iniciando STT: model={model_name}, device={device}, compute_type={compute_type} ---",
        flush=True,
    )
    print(
        f"RAM antes de cargar: {ram_before_mb:.2f} MB | VRAM antes: {vram_before_mb:.2f} MB",
        flush=True,
    )

    # 1. Medir tiempo de carga del modelo (Cold Load)
    t0 = time.perf_counter()
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    load_time_ms = (time.perf_counter() - t0) * 1000.0

    ram_after_load_mb = process.memory_info().rss / (1024 * 1024)
    vram_after_load_mb = get_vram_usage_mb() if device == "cuda" else 0.0
    print(f"Modelo cargado en: {load_time_ms:.2f} ms", flush=True)
    print(
        f"RAM tras carga: {ram_after_load_mb:.2f} MB | VRAM tras carga: {vram_after_load_mb:.2f} MB",
        flush=True,
    )

    config_results = {
        "model_name": model_name,
        "device": device,
        "compute_type": compute_type,
        "load_time_ms": round(load_time_ms, 2),
        "ram_before_mb": round(ram_before_mb, 2),
        "ram_after_load_mb": round(ram_after_load_mb, 2),
        "vram_before_mb": round(vram_before_mb, 2),
        "vram_after_load_mb": round(vram_after_load_mb, 2),
        "phrases": [],
    }

    total_audio_duration = 0.0
    total_inference_time = 0.0

    # 2. Transcribir cada archivo de audio
    for phrase_id, meta in GROUND_TRUTH.items():
        wav_path = os.path.join(audio_dir, f"{phrase_id}.wav")
        if not os.path.exists(wav_path):
            print(f"  [AVISO] Archivo no encontrado: {wav_path}", flush=True)
            continue

        with wave.open(wav_path, "rb") as wf:
            duration_s = wf.getnframes() / float(wf.getframerate())

        t_inf_start = time.perf_counter()
        segments, info = model.transcribe(wav_path, language="es", beam_size=5)
        transcribed_text = " ".join([seg.text.strip() for seg in segments])
        inference_time_s = time.perf_counter() - t_inf_start
        inference_time_ms = inference_time_s * 1000.0

        rtf = inference_time_s / duration_s if duration_s > 0 else 0.0
        total_audio_duration += duration_s
        total_inference_time += inference_time_s

        # Comprobar presencia de palabras clave
        keywords_matched = [
            kw for kw in meta["keywords"] if kw.lower() in transcribed_text.lower()
        ]
        keyword_accuracy = len(keywords_matched) / len(meta["keywords"])

        phrase_eval = {
            "phrase_id": phrase_id,
            "category": meta["category"],
            "reference_text": meta["text"],
            "transcribed_text": transcribed_text,
            "duration_seconds": round(duration_s, 3),
            "inference_time_ms": round(inference_time_ms, 2),
            "rtf": round(rtf, 4),
            "language_detected": info.language,
            "language_probability": round(info.language_probability, 4),
            "keywords_total": len(meta["keywords"]),
            "keywords_matched": len(keywords_matched),
            "keyword_accuracy_ratio": round(keyword_accuracy, 2),
        }
        config_results["phrases"].append(phrase_eval)
        print(
            f"  [{phrase_id}] Inferencia: {inference_time_ms:.1f} ms | Duración: {duration_s:.2f} s | RTF: {rtf:.4f}",
            flush=True,
        )
        print(f"       Ref : {meta['text']}", flush=True)
        print(f"       STT : {transcribed_text}", flush=True)

    ram_final_mb = process.memory_info().rss / (1024 * 1024)
    vram_final_mb = get_vram_usage_mb() if device == "cuda" else 0.0
    overall_rtf = (
        total_inference_time / total_audio_duration if total_audio_duration > 0 else 0.0
    )

    config_results["ram_final_mb"] = round(ram_final_mb, 2)
    config_results["vram_final_mb"] = round(vram_final_mb, 2)
    config_results["total_audio_duration_seconds"] = round(total_audio_duration, 3)
    config_results["total_inference_time_seconds"] = round(total_inference_time, 3)
    config_results["overall_rtf"] = round(overall_rtf, 4)

    return config_results


def run_full_stt_benchmark(output_json: str = "output/stt_results.json"):
    print("=" * 60, flush=True)
    print("INICIANDO BENCHMARK COMPLETO STT — FASTER-WHISPER", flush=True)
    print("Comparativa: Modelos 'base' vs 'small' en CPU y CUDA", flush=True)
    print("=" * 60, flush=True)

    configs_to_test = [
        ("base", "cpu", "int8"),
        ("base", "cuda", "float16"),
        ("small", "cpu", "int8"),
        ("small", "cuda", "float16"),
    ]

    all_benchmarks = []
    for model_name, device, compute_type in configs_to_test:
        try:
            res = run_stt_benchmark_for_config(model_name, device, compute_type)
            all_benchmarks.append(res)
        except (RuntimeError, ValueError, OSError) as e:
            print(
                f"[ERROR] Falló configuración {model_name} {device} {compute_type}: {e}",
                flush=True,
            )
            all_benchmarks.append(
                {
                    "model_name": model_name,
                    "device": device,
                    "compute_type": compute_type,
                    "error": str(e),
                }
            )

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_benchmarks, f, ensure_ascii=False, indent=2)

    print("=" * 60, flush=True)
    print(
        f"BENCHMARK STT COMPLETADO. Resultados guardados en: {output_json}", flush=True
    )
    print("=" * 60, flush=True)
    return all_benchmarks


if __name__ == "__main__":
    run_full_stt_benchmark()
