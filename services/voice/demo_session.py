"""Demostración interactiva de sesión conversacional continua multi-turno (Incremento 3.2).

Permite mantener un diálogo continuo en tiempo real con el asistente virtual:
VAD (micrófono) -> STT (Whisper) -> Cerebro Comercial -> TTS (Piper) -> Altavoz -> VAD (siguiente turno)

Uso:
  uv run python demo_session.py
  uv run python demo_session.py --max-turns 4 --device 0
"""

import argparse

from voice.audio_capture import check_audio_hardware
from voice.pipeline import ConversationTurnPipeline
from voice.session import ConversationSession, SessionConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Demostración de conversación continua multi-turno (Incremento 3.2)")
    parser.add_argument("--device", type=int, default=None, help="Índice opcional del dispositivo de audio")
    parser.add_argument("--max-turns", type=int, default=None, help="Número máximo de turnos antes de cerrar la sesión")
    parser.add_argument("--max-timeouts", type=int, default=3, help="Máximo de silencios consecutivos permitidos")
    args = parser.parse_args()

    print("=" * 70)
    print("SESIÓN CONVERSACIONAL CONTINUA MULTI-TURNO — INCREMENTO 3.2")
    print("=" * 70)

    # 1. Diagnóstico de hardware
    hw = check_audio_hardware(device=args.device)
    print(f"[Hardware] Micrófono: {'DISPONIBLE' if hw.has_input_device else 'NO DISPONIBLE'} ({hw.input_device_name or 'N/A'})")
    print(f"[Hardware] Altavoz  : {'DISPONIBLE' if hw.has_output_device else 'NO DISPONIBLE'} ({hw.output_device_name or 'N/A'})")

    if not hw.has_input_device:
        print("\n[Error] No se ha detectado dispositivo de entrada (micrófono) en WSL2/WSLg.")
        return

    # 2. Configuración de sesión
    config = SessionConfig(
        device=args.device,
        max_turns=args.max_turns,
        max_consecutive_timeouts=args.max_timeouts,
        session_output_dir="output/interactive_sessions",
    )

    # 3. Inicialización del pipeline
    pipeline = ConversationTurnPipeline(
        stt_model_name="small",
        stt_device="cpu",
        stt_compute_type="int8",
        tts_model_path="models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx",
        tts_config_path="models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx.json",
    )

    session = ConversationSession(pipeline=pipeline, config=config)

    print("\nINSTRUCCIONES DE INTERACCIÓN:")
    print("- Habla con naturalidad cuando veas '[Sesión] Escuchando...'")
    print("- Tras cada respuesta del asistente, volverá a escuchar automáticamente.")
    print("- Para finalizar la sesión, puedes:")
    print("  * Decir 'terminar llamada', 'adiós' o 'finalizar conversación'.")
    print("  * Decir 'no me llaméis más' (activa DNC comercial y cierre inmediato).")
    print("  * Pulsar Ctrl+C en cualquier momento para salir limpiamente.\n")

    telemetry = session.run()

    print("=" * 70)
    print(f"RESUMEN FINAL DE SESIÓN: {telemetry.session_id}")
    print(f"- Turnos completados  : {telemetry.total_turns}")
    print(f"- Causa de finalización: {telemetry.end_reason.value}")
    print(f"- Duración total      : {telemetry.total_wall_time_s} s")
    if telemetry.context:
        print(f"- DNC registrado      : {telemetry.context.is_do_not_contact}")
        print(f"- Rechazo registrado  : {telemetry.context.is_rejected}")
    print(f"- Grabaciones en      : {session.session_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()
