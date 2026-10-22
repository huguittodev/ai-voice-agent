"""Pruebas automatizadas de regresión para los componentes de STT y TTS."""

import json
import os
import wave

import pytest

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def test_tts_audio_files_exist():
    """Comprueba que se han generado los 5 audios comerciales de Piper si existen en disco."""
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    if not os.path.exists(audio_dir):
        pytest.skip(f"Directorio de audio no encontrado: {audio_dir} (requiere benchmark TTS previo)")
    for i in range(1, 6):
        wav_file = os.path.join(audio_dir, f"frase_{i}.wav")
        if not os.path.exists(wav_file):
            pytest.skip(f"Falta el archivo {wav_file} (requiere benchmark TTS previo)")
        assert os.path.getsize(wav_file) > 10000, (
            f"El archivo {wav_file} es demasiado pequeño"
        )
        with wave.open(wav_file, "rb") as wf:
            assert wf.getframerate() == 22050
            assert wf.getnchannels() == 1
            assert wf.getnframes() > 0


def test_tts_results_valid():
    """Comprueba que los resultados de benchmark TTS tienen métricas reales si existen en disco."""
    results_path = os.path.join(OUTPUT_DIR, "tts_results.json")
    if not os.path.exists(results_path):
        pytest.skip(f"Falta {results_path} (requiere benchmark TTS previo)")
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["phrases"]) == 5
    assert data["overall_rtf"] < 0.1, "El RTF de Piper en CPU debería ser < 0.10"
    assert data["total_audio_duration_seconds"] > 25.0


def test_stt_results_valid():
    """Comprueba que el benchmark STT contiene transcripciones válidas si existe en disco."""
    results_path = os.path.join(OUTPUT_DIR, "stt_results.json")
    if not os.path.exists(results_path):
        pytest.skip(f"Falta {results_path} (requiere benchmark STT previo)")
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) >= 2
    # El modelo small en CPU debe tener resultados
    small_cpu = next(
        (
            item
            for item in data
            if item["model_name"] == "small" and item["device"] == "cpu"
        ),
        None,
    )
    assert small_cpu is not None
    assert len(small_cpu["phrases"]) == 5
    assert small_cpu["overall_rtf"] < 0.35, (
        "El RTF de small en CPU i9 debería ser < 0.35"
    )


def test_tts_sharvard_audio_files_exist():
    """Comprueba que se han generado los 5 audios comerciales de Piper con voz sharvard si existen en disco."""
    audio_dir = os.path.join(OUTPUT_DIR, "audio_sharvard")
    if not os.path.exists(audio_dir):
        pytest.skip(f"Directorio de audio sharvard no encontrado: {audio_dir}")
    for i in range(1, 6):
        wav_file = os.path.join(audio_dir, f"frase_{i}.wav")
        if not os.path.exists(wav_file):
            pytest.skip(f"Falta el archivo {wav_file}")
        assert os.path.getsize(wav_file) > 10000, (
            f"El archivo {wav_file} es demasiado pequeño"
        )
        with wave.open(wav_file, "rb") as wf:
            assert wf.getframerate() == 22050
            assert wf.getnchannels() == 1
            assert wf.getnframes() > 0


def test_tts_sharvard_results_valid():
    """Comprueba que los resultados de sharvard tienen métricas y licencia válidas si existen en disco."""
    results_path = os.path.join(OUTPUT_DIR, "tts_sharvard_results.json")
    if not os.path.exists(results_path):
        pytest.skip(f"Falta {results_path}")
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["phrases"]) == 5
    assert data["voice_name"] == "es_ES-sharvard-medium"
    assert data["license"] == "MIT"
    assert data["overall_rtf"] < 0.1
