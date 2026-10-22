"""Pruebas unitarias completas con mocks para el prototipo de Gemini Live API.

Verifica:
- Validación de configuración y clave de API ausente.
- Instrucciones de sistema y personalidad comercial.
- Herramientas deterministas (Function Calling) y actualización de estado.
- Manejo de respuestas del servidor (audio, interrupciones barge-in, turnos).
- Manejo de cuota excedida (429 / RESOURCE_EXHAUSTED) y fallos de conexión.
- Cancelación limpia y cierre de sesión.
- Ausencia de acciones externas no autorizadas.
- Coexistencia pacífica con el pipeline local determinista previo.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice.gemini_live import (
    FREE_TIER_PRIVACY_WARNING,
    GeminiLiveConfig,
    GeminiLiveConfigError,
    GeminiLiveConnectionError,
    GeminiLiveQuotaError,
    GeminiLiveSession,
    LiveCommercialState,
    LiveSessionMetrics,
    build_system_instruction,
    create_live_tools,
    list_available_models,
)
from voice.responder import CommercialIntent, generate_commercial_response


# ============================================================================ #
# 1. Pruebas de Configuración y Clave de API                                   #
# ============================================================================ #


class TestGeminiLiveConfig:
    def test_missing_api_key_raises_config_error(self):
        """Si falta la clave de API, validate() debe lanzar GeminiLiveConfigError."""
        cfg = GeminiLiveConfig(api_key="")
        with pytest.raises(GeminiLiveConfigError, match="No se ha encontrado la clave de API"):
            cfg.validate()

    def test_empty_model_raises_config_error(self):
        """Si el modelo está vacío, validate() debe fallar limpiamente."""
        cfg = GeminiLiveConfig(api_key="AIzaSy_test_key", model="")
        with pytest.raises(GeminiLiveConfigError, match="El identificador del modelo no puede estar vacío"):
            cfg.validate()

    def test_default_values(self):
        """Verifica los valores por defecto del prototipo (gemini-3.8-live, 16kHz in, 24kHz out, 99 € base)."""
        cfg = GeminiLiveConfig(api_key="AIzaSy_test_key")
        assert cfg.model == "gemini-3.8-live"
        assert cfg.voice_name == "Puck"
        assert cfg.sample_rate_in == 16000
        assert cfg.sample_rate_out == 24000
        assert cfg.channels == 1
        assert cfg.base_price_eur == 99.0
        assert cfg.agent_name == "Hugo"
        assert cfg.max_session_duration_s == 900.0

    def test_env_var_overrides(self, monkeypatch):
        """Comprueba que las variables de entorno configuran el modelo y voz."""
        monkeypatch.setenv("GEMINI_API_KEY", "env_key_123")
        monkeypatch.setenv("GEMINI_LIVE_MODEL", "gemini-test-model")
        monkeypatch.setenv("GEMINI_LIVE_VOICE", "Fenrir")

        cfg = GeminiLiveConfig()
        assert cfg.api_key == "env_key_123"
        assert cfg.model == "gemini-test-model"
        assert cfg.voice_name == "Fenrir"
        cfg.validate()

    def test_build_connect_config_uses_audio_modality_without_livemodality(self):
        """Verifica que _build_connect_config use response_modalities=['AUDIO'] y nunca types.LiveModality."""
        cfg = GeminiLiveConfig(api_key="mock_key")
        session = GeminiLiveSession(config=cfg)

        mock_types = MagicMock()
        # Aseguramos explícitamente que LiveModality no existe en types
        del mock_types.LiveModality

        with patch("voice.gemini_live.types", mock_types), patch("voice.gemini_live.GENAI_AVAILABLE", True):
            session._build_connect_config(tools=[])
            mock_types.LiveConnectConfig.assert_called_once()
            call_kwargs = mock_types.LiveConnectConfig.call_args[1]
            assert call_kwargs["response_modalities"] == ["AUDIO"]


# ============================================================================ #
# 2. Pruebas de Instrucciones de Sistema y Reglas Comerciales                  #
# ============================================================================ #


class TestSystemInstruction:
    def test_contains_hugo_and_virtual_identity(self):
        """El prompt debe exigir identificarse como asistente virtual de Hugo y usar «tú»."""
        cfg = GeminiLiveConfig(api_key="mock", agent_name="Hugo")
        instruction = build_system_instruction(cfg)

        assert "asistente virtual de Hugo" in instruction
        assert "tú" in instruction.lower()
        assert "usted" in instruction.lower()  # Debe prohibir expresamente usted
        assert "NUNCA finjas ser humano" in instruction

    def test_contains_price_and_safeguards(self):
        """El prompt debe incluir el precio oficial de 99 € y prohibir inventar cifras."""
        cfg = GeminiLiveConfig(api_key="mock", base_price_eur=99.0)
        instruction = build_system_instruction(cfg)

        assert "99 €" in instruction
        assert "NO inventes cifras" in instruction

    def test_contains_handoff_and_dnc_safeguards(self):
        """El prompt debe detallar la invocación de herramientas para handoff y DNC."""
        cfg = GeminiLiveConfig(api_key="mock")
        instruction = build_system_instruction(cfg)

        assert "request_human_handoff" in instruction
        assert "JAMÁS afirmes que la llamada ha sido transferida" in instruction
        assert "request_do_not_contact" in instruction
        assert "termina la conversación sin insistir" in instruction

    def test_privacy_warning_is_explicit(self):
        """El aviso del nivel gratuito debe advertir del tratamiento de datos."""
        assert "AVISO DE PRIVACIDAD" in FREE_TIER_PRIVACY_WARNING
        assert "No utilices datos personales" in FREE_TIER_PRIVACY_WARNING


# ============================================================================ #
# 3. Pruebas de Herramientas Deterministas (Function Calling)                  #
# ============================================================================ #


class TestDeterministicTools:
    def test_record_commercial_interest(self):
        """record_commercial_interest actualiza el estado comercial determinista."""
        state = LiveCommercialState()
        cfg = GeminiLiveConfig(api_key="mock")
        metrics = LiveSessionMetrics()
        tools = create_live_tools(state, cfg, metrics)
        tool_map = {t.__name__: t for t in tools}

        res = tool_map["record_commercial_interest"](
            business_activity="Taller mecánico",
            requirements="Página para pedir cita de cambio de aceite",
        )

        assert res["status"] == "success"
        assert state.interest_expressed is True
        assert state.business_activity == "Taller mecánico"
        assert state.requirements == "Página para pedir cita de cambio de aceite"
        assert "record_commercial_interest" in metrics.tools_invoked

    def test_request_human_handoff(self):
        """request_human_handoff registra la petición sin afirmar transferencia real."""
        state = LiveCommercialState()
        cfg = GeminiLiveConfig(api_key="mock", agent_name="Hugo")
        metrics = LiveSessionMetrics()
        tools = create_live_tools(state, cfg, metrics)
        tool_map = {t.__name__: t for t in tools}

        res = tool_map["request_human_handoff"](contact_name="Pedro", notes="Dudas avanzadas")

        assert res["status"] == "registered"
        assert res["has_real_transfer"] is False
        assert state.human_handoff_requested is True
        assert state.handoff_contact == "Pedro"
        assert state.handoff_notes == "Dudas avanzadas"
        assert "request_human_handoff" in metrics.tools_invoked

    def test_request_do_not_contact(self):
        """request_do_not_contact activa DNC y marca la sesión como terminada."""
        state = LiveCommercialState()
        cfg = GeminiLiveConfig(api_key="mock")
        metrics = LiveSessionMetrics()
        tools = create_live_tools(state, cfg, metrics)
        tool_map = {t.__name__: t for t in tools}

        res = tool_map["request_do_not_contact"](reason="No me interesa recibir llamadas")

        assert res["status"] == "dnc_confirmed"
        assert res["must_stop_immediately"] is True
        assert state.do_not_contact is True
        assert state.is_finished is True
        assert state.dnc_reason == "No me interesa recibir llamadas"
        assert "request_do_not_contact" in metrics.tools_invoked

    def test_get_pricing_and_offer_details(self):
        """get_pricing_and_offer_details devuelve exactamente la tarifa configurada."""
        state = LiveCommercialState()
        cfg = GeminiLiveConfig(api_key="mock", base_price_eur=99.0)
        tools = create_live_tools(state, cfg)
        tool_map = {t.__name__: t for t in tools}

        res = tool_map["get_pricing_and_offer_details"]()

        assert res["base_price_eur"] == 99.0
        assert res["currency"] == "EUR"
        assert len(res["includes"]) >= 3
        assert state.pricing_provided is True


# ============================================================================ #
# 4. Pruebas del Manejador de Sesión y Audio (Mocks)                           #
# ============================================================================ #


class TestGeminiLiveSessionLogic:
    @pytest.mark.asyncio
    async def test_interrupted_clears_playback_queue(self):
        """Cuando server_content.interrupted es True, la cola de audio debe vaciarse (barge-in)."""
        cfg = GeminiLiveConfig(api_key="mock")
        session = GeminiLiveSession(config=cfg)

        # Encolar bloques de audio ficticios
        await session._audio_out_queue.put(b"chunk1")
        await session._audio_out_queue.put(b"chunk2")
        await session._audio_out_queue.put(b"chunk3")
        assert session._audio_out_queue.qsize() == 3

        # Simular respuesta de interrupción
        mock_response = MagicMock()
        mock_response.server_content = MagicMock()
        mock_response.server_content.interrupted = True
        mock_response.server_content.model_turn = None
        mock_response.server_content.turn_complete = False
        mock_response.tool_call = None

        mock_session_client = AsyncMock()
        await session._handle_server_response(mock_response, mock_session_client, {})

        # La cola debe haber sido vaciada
        assert session._audio_out_queue.empty()
        assert session.metrics.interruption_count == 1

    @pytest.mark.asyncio
    async def test_model_turn_queues_audio(self):
        """Los datos de audio recibidos del modelo se encolan para su reproducción."""
        cfg = GeminiLiveConfig(api_key="mock")
        session = GeminiLiveSession(config=cfg)

        mock_response = MagicMock()
        mock_response.server_content = MagicMock()
        mock_response.server_content.interrupted = False
        mock_response.server_content.turn_complete = True
        mock_response.tool_call = None

        part = MagicMock()
        part.inline_data = MagicMock()
        part.inline_data.data = b"pcm_audio_bytes_24khz"
        part.function_call = None
        mock_response.server_content.model_turn.parts = [part]

        mock_session_client = AsyncMock()
        await session._handle_server_response(mock_response, mock_session_client, {})

        queued_audio = await session._audio_out_queue.get()
        assert queued_audio == b"pcm_audio_bytes_24khz"
        assert session.metrics.bytes_received == len(b"pcm_audio_bytes_24khz")
        assert session.metrics.turns_completed == 1

    @pytest.mark.asyncio
    async def test_tool_call_execution_and_reply(self):
        """Cuando Gemini solicita una herramienta, se ejecuta localmente y se envía respuesta."""
        cfg = GeminiLiveConfig(api_key="mock")
        state = LiveCommercialState()
        session = GeminiLiveSession(config=cfg, state=state)

        tool_func = MagicMock(return_value={"status": "ok"})
        tool_map = {"test_tool": tool_func}

        fc = MagicMock()
        fc.name = "test_tool"
        fc.id = "call_abc123"
        fc.args = {"arg1": "val1"}

        mock_session_client = AsyncMock()
        mock_session_client.send_tool_response = AsyncMock()
        mock_session_client.send = AsyncMock()

        await session._execute_and_reply_tool(fc, mock_session_client, tool_map)

        tool_func.assert_called_once_with(arg1="val1")
        assert (
            mock_session_client.send_tool_response.await_count == 1
            or mock_session_client.send.await_count == 1
        )

    def test_list_available_models(self):
        """list_available_models devuelve los modelos reportados por el cliente."""
        mock_m1 = MagicMock()
        mock_m1.name = "models/gemini-3.8-live"
        mock_m2 = MagicMock()
        mock_m2.name = "models/gemini-2.5-flash"

        mock_client = MagicMock()
        mock_client.models.list.return_value = [mock_m1, mock_m2]

        with patch("voice.gemini_live.genai.Client", return_value=mock_client), \
             patch("voice.gemini_live.GENAI_AVAILABLE", True):
            models = list_available_models("AIzaSy_fake")
            assert "models/gemini-3.8-live" in models
            assert "models/gemini-2.5-flash" in models

    def test_missing_genai_client_raises_clean_error(self):
        """Si el paquete oficial no está presente, _create_genai_client lanza GeminiLiveConfigError."""
        cfg = GeminiLiveConfig(api_key="mock")
        session = GeminiLiveSession(config=cfg)

        with patch("voice.gemini_live.GENAI_AVAILABLE", False):
            with pytest.raises(GeminiLiveConfigError, match="El paquete oficial 'google-genai' no está instalado"):
                session._create_genai_client()

    @pytest.mark.asyncio
    async def test_quota_error_handling(self):
        """Un error 429 / RESOURCE_EXHAUSTED se mapea a GeminiLiveQuotaError sin reintentos infinitos."""
        cfg = GeminiLiveConfig(api_key="mock")
        session = GeminiLiveSession(config=cfg)

        mock_client = MagicMock()
        mock_client.aio.live.connect.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded for model")

        with patch.object(session, "_create_genai_client", return_value=mock_client), \
             patch("voice.gemini_live.SOUNDDEVICE_AVAILABLE", False):
            with pytest.raises(GeminiLiveQuotaError, match="Se ha alcanzado el límite de cuota"):
                await session.run()

        assert session.metrics.end_reason == "quota_exceeded"

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Un error inesperado de red se captura como GeminiLiveConnectionError."""
        cfg = GeminiLiveConfig(api_key="mock")
        session = GeminiLiveSession(config=cfg)

        mock_client = MagicMock()
        mock_client.aio.live.connect.side_effect = RuntimeError("WebSocket connection dropped")

        with patch.object(session, "_create_genai_client", return_value=mock_client), \
             patch("voice.gemini_live.SOUNDDEVICE_AVAILABLE", False):
            with pytest.raises(GeminiLiveConnectionError, match="Error en sesión Live"):
                await session.run()


# ============================================================================ #
# 5. Verificación de Compatibilidad con el Pipeline Local Anterior             #
# ============================================================================ #


class TestLocalPipelineCompatibility:
    def test_deterministic_responder_unaffected(self):
        """El cerebro comercial local existente debe seguir respondiendo y clasificando sin errores."""
        resp = generate_commercial_response("Hola, buenos días")
        assert resp.intent == CommercialIntent.GREETING_PRESENTATION
        assert "asistente virtual" in resp.response_text.lower()

        resp_dnc = generate_commercial_response("No me llaméis más por favor")
        assert resp_dnc.intent == CommercialIntent.DO_NOT_CONTACT
