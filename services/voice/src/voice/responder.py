"""Módulo de respuesta comercial determinista mediante reglas, clasificación de intenciones y gestión de estados (Fase 2).

Implementa el Cerebro Comercial de la Fase 2, cumpliendo rigurosamente con AGENTS.md:
- No inventar precios, tarifas, disponibilidad de agenda ni compromisos comerciales.
- Identificarse siempre como asistente virtual (nunca presentarse como humano).
- Tratar cualquier solicitud de reunión como una propuesta pendiente de confirmación.
- Gestión prioritaria e irreversible del estado de exclusión y bajas (DO_NOT_CONTACT).
- Distinguir entre rechazo suave (soft_rejection) y solicitud expresa de baja (do_not_contact).
- Soporte para conversaciones multi-turno con gestión de estado sin base de datos pesada.
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class CommercialIntent(str, Enum):
    # 1. Saludo y presentación
    GREETING_PRESENTATION = "greeting_presentation"
    # 2. Información del servicio
    SERVICE_INFO = "service_info"
    # 3. Expresión de interés / dossier
    EXPRESS_INTEREST = "express_interest"
    # 4. Solicitud de reunión / demo
    MEETING_REQUEST = "meeting_request"
    # 5. Pregunta de precio / objeción presupuestaria
    PRICE_INQUIRY = "price_inquiry"
    # 6. Falta de tiempo / ocupado
    BUSY_CALL_LATER = "busy_call_later"
    # 7. Competidor existente / proveedor actual
    EXISTING_COMPETITOR = "existing_competitor"
    # 8. Rechazo comercial sin baja explícita
    SOFT_REJECTION = "soft_rejection"
    # 9. Solicitud expresa de no contacto / baja (DNC)
    DO_NOT_CONTACT = "do_not_contact"
    # 10. Petición de rellamada en horario propuesto
    CALLBACK_REQUEST = "callback_request"
    # 11. Petición de transferencia a persona humana
    TRANSFER_HUMAN = "transfer_human"
    # 12. Dudas de privacidad y RGPD
    PRIVACY_INQUIRY = "privacy_inquiry"
    # 13. Integraciones técnicas / APIs
    TECHNICAL_INTEGRATION = "technical_integration"
    # 14. Disponibilidad de agenda
    SCHEDULE_AVAILABILITY = "schedule_availability"
    # 15. Información desconocida / fuera de alcance
    UNKNOWN_INFO = "unknown_info"
    # 16. Retirada de interés previa / arrepentimiento
    INTEREST_WITHDRAWAL = "interest_withdrawal"
    # 17. Ininteligible / silencio / ruido
    UNINTELLIGIBLE = "unintelligible"
    # 18. Fallback / ambiguo / fuera de dominio
    FALLBACK_CLARIFICATION = "fallback_clarification"


@dataclass
class ConversationContext:
    """Modelo de estado conversacional en memoria para evaluación multi-turno."""
    history: list[tuple[str, str]] = field(default_factory=list)
    current_intent: CommercialIntent | None = None
    previous_intent: CommercialIntent | None = None
    is_do_not_contact: bool = False
    is_rejected: bool = False
    interest_expressed: bool = False
    meeting_requested: bool = False
    turn_count: int = 0

    def record_turn(self, user_text: str, agent_reply: str, intent: CommercialIntent) -> None:
        self.history.append((user_text, agent_reply))
        self.previous_intent = self.current_intent
        self.current_intent = intent
        self.turn_count += 1
        if intent == CommercialIntent.DO_NOT_CONTACT:
            self.is_do_not_contact = True
            self.is_rejected = True
        elif intent == CommercialIntent.SOFT_REJECTION:
            self.is_rejected = True
        elif intent == CommercialIntent.EXPRESS_INTEREST:
            self.interest_expressed = True
        elif intent == CommercialIntent.MEETING_REQUEST:
            self.meeting_requested = True
        elif intent == CommercialIntent.INTEREST_WITHDRAWAL:
            self.interest_expressed = False
            self.meeting_requested = False
            self.is_rejected = True


@dataclass(frozen=True)
class CommercialResponse:
    """Estructura inmutable de respuesta emitida por el motor de decisión."""
    intent: CommercialIntent
    response_text: str
    confidence: float
    matched_patterns: list[str]
    is_do_not_contact: bool = False
    context: ConversationContext | None = None


# --- CATÁLOGO DE PATRONES DETERMINISTAS ---

_PATTERNS_DO_NOT_CONTACT: list[str] = [
    r"\bno\s+(me\s+|nos\s+)?(volv\w*\s+a\s+llamar|llam\w*\s+m[aá]s|contact\w*\s+m[aá]s|molest\w*)\b",
    r"\bno\s+(me\s+|nos\s+)?(llames|llame|llam[eé]is|llamen|contactes|contacte)\b",
    r"\bborr\w*\s+(mi\s+|nuestro\s+)?(n[uú]mero|contacto|datos|tel[eé]fono)\b",
    r"\b(da[rd]\w*|dar)\s+de\s+baja\b",
    r"\bno\s+quiero\s+(m[aá]s\s+)?(llamadas|contacto|mensajes)\b",
    r"\belimin\w*\s+(mi\s+n[uú]mero\s+)?de\s+(la|vuestra)\s+lista\b",
    r"\blista\s+robinson\b",
    r"\bno\s+volv\w*\s+(a\s+)?llamar\b",
]

_PATTERNS_INTEREST_WITHDRAWAL: list[str] = [
    r"\bpens[aá]ndolo\s+bien\s+(ya\s+no|mejor\s+no|lo\s+dejamos)\b",
    r"\bya\s+no\s+(me\s+|nos\s+)?interesa\b",
    r"\bcancel\w*\s+(la\s+)?(cita|reuni[oó]n|solicitud|petici[oó]n|informaci[oó]n)\b",
    r"\bolv[ií]da(lo|te)|d[eé]jalo\b",
    r"\bal\s+final\s+(no|nada|lo\s+dejamos)\b",
    r"\bme\s+he\s+arrepentido\b",
]

_PATTERNS_TRANSFER_HUMAN: list[str] = [
    r"\b(pas\w*|hablar)\s+(con\s+)?(una\s+persona|un\s+humano|alguien\s+real|un\s+operador|un\s+agente\s+humano)\b",
    r"\bpas\w*\s+con\s+(tu\s+)?(jefe|responsable|superior|encargado)\b",
    r"\bquiero\s+hablar\s+con\s+(una\s+persona|alguien\s+de\s+verdad|alguien\s+humano)\b",
    r"\beres\s+(un\s+)?robot\b",
]

_PATTERNS_PRIVACY_INQUIRY: list[str] = [
    r"\bde\s+d[oó]nde\s+(hab[eé]is|has|han)\s+sacado\s+(mi\s+)?(n[uú]mero|tel[eé]fono|datos)\b",
    r"\bc[oó]mo\s+ten[eé]is\s+(mi\s+)?(n[uú]mero|tel[eé]fono|contacto)\b",
    r"\bpol[ií]tica\s+de\s+privacidad\b",
    r"\b(protecci[oó]n\s+de\s+datos|rgpd|lopd)\b",
    r"\bqu[eé]\s+hac\w*\b.*\bdatos\b",
]

_PATTERNS_PRICE_INQUIRY: list[str] = [
    r"\bcu[aá]nto\s+(cuesta|vale|cobran|sale)\b",
    r"\bqu[eé]\s+precio\s+tiene\b",
    r"\b(tarifas?|precios?|costes?|costos?)\b",
    r"\bno\s+tenemos\s+presupuesto\b",
    r"\b(es|parece|ser[aá]|resulta|va\s+a\s+ser)\s+(muy\s+)?car[oa]s?\b",
]

_PATTERNS_BUSY_CALL_LATER: list[str] = [
    r"\bahora\s+no\s+puedo\s+hablar\b",
    r"\bestoy\s+(muy\s+)?(ocupado|liado)\b",
    r"\bestoy\s+con\s+un\s+cliente\b",
    r"\bestoy\s+en\s+una\s+reuni[oó]n\b",
    r"\bpill\w*\s+mal\b",
    r"\ben\s+mal\s+momento\b",
    r"\bahora\s+mismo\s+imposible\b",
    r"\bimposible\s+atender\w*\b",
]

_PATTERNS_CALLBACK_REQUEST: list[str] = [
    r"\b(ll[aá]m\w*|habl\w*)\s+(luego|m[aá]s\s+tarde|mañana|el\s+(pr[oó]ximo\s+)?\w+|la\s+semana\s+que\s+viene|por\s+la\s+tarde|en\s+otro\s+momento)\b",
    r"\bpuedes\s+llamar\s+(m[aá]s\s+tarde|luego|mañana)\b",
    r"\bllamadme\s+(a\s+las\s+\d+|en\s+otro\s+momento)\b",
]

_PATTERNS_EXISTING_COMPETITOR: list[str] = [
    r"\bya\s+(trabajamos|tenemos|usamos|utilizamos|contamos)\s+(con\s+)?(otro|otra|un|una|proveedor|servicio|sistema|empresa|software|herramienta|salesforce|hubspot)\b",
    r"\b(estamos\s+contentos\s+con\s+)?nuestro\s+proveedor\b",
    r"\bya\s+lo\s+tenemos\s+cubierto\b",
]

_PATTERNS_SOFT_REJECTION: list[str] = [
    r"\bno\s+(nos\s+|me\s+)?interesa\b",
    r"\bno\s+(nos\s+|me\s+)?encaja\b",
    r"\bno\s+lo\s+vemos\s+viable\b",
    r"\bno\s+lo\s+necesitamos\b",
    r"\bde\s+momento\s+no\b",
    r"\bgracias\s+pero\s+no\b",
    r"\bno\s+gracias\b",
]

_PATTERNS_TECHNICAL_INTEGRATION: list[str] = [
    r"\bse\s+integra\s+con\b",
    r"\bten[eé]is\s+integraci[oó]n\b",
    r"\bconect\w*\s+con\s+(nuestro\s+)?(crm|erp|software|sistema|sap|hubspot|salesforce|woocommerce)\b",
    r"\bdispon[eé]is\s+de\s+apis?\b",
    r"\bten[eé]is\s+apis?\b",
    r"\bwebhooks?\b",
    r"\bes\s+compatible\s+con\b",
]

_PATTERNS_SCHEDULE_AVAILABILITY: list[str] = [
    r"\bqu[eé]\s+d[ií]as\s+ten[eé]is\s+(libres?|disponibles?)\b",
    r"\bten[eé]is\s+hueco\b",
    r"\bcu[aá]ndo\s+ten[eé]is\s+agenda\b",
    r"\bqu[eé]\s+horarios?\s+hay\s+disponibles?\b",
    r"\best[aá]is\s+disponibles?\s+(mañana|hoy|el\s+\w+)\b",
]

_PATTERNS_MEETING_REQUEST: list[str] = [
    r"\b(reuni[oó]n|reunirnos|quedar|vernos)\b",
    r"\bagendar\b",
    r"\b(llamada|videollamada|conferencia)\b",
    r"\b(hacer|tener|ver|pedir)?\s*(una\s+)?(demo|demostraci[oó]n|cita)\b",
    r"\bcu[aá]ndo\s+podemos\s+hablar\b",
]

_PATTERNS_EXPRESS_INTEREST: list[str] = [
    r"\bme\s+interesa\b",
    r"\bestoy\s+interesad[oa]\b",
    r"\b(envi|mand|recib)\w*\s+(un\s+)?(correo|email|dossier|cat[aá]logo|informaci[oó]n|detalles)\b",
    r"\b(envi|mand)\w*\s+(m[aá]s\s+)?(informaci[oó]n|detalles)\b",
    r"\bquiero\s+m[aá]s\s+(detalles|informaci[oó]n)\b",
    r"\bsuena\s+bien\b",
    r"\bparece\s+interesante\b",
]

_PATTERNS_SERVICE_INFO: list[str] = [
    r"\bqu[eé]\s+(servicios?|hac[eé]is|ofrec[eé]is|ten[eé]is|hacen)\b",
    r"\bcu[aá]l\s+es\s+vuestro\s+(servicio|producto|negocio)\b",
    r"\binformaci[oó]n\s+(sobre|de)\s+(vuestros?|los)\s+servicios?\b",
    r"\bde\s+qu[eé]\s+se\s+trata\b",
    r"\bc[oó]mo\s+funciona\b",
    r"\ba\s+qu[eé]\s+os\s+dedic[aá]is\b",
]

_PATTERNS_UNKNOWN_INFO: list[str] = [
    r"\bd[oó]nde\s+est[aá]\s+vuestra\s+(sede|oficina)(\s+central)?\s+en\b",
    r"\bcu[aá]nto\s+factur\w*\b",
    r"\bcu[aá]ntos\s+empleados\s+sois\b",
    r"\bqui[eé]n\s+es\s+vuestro\s+(ceo|director|dueño)\b",
]

_PATTERNS_GREETING_PRESENTATION: list[str] = [
    r"\b(hola|buenos\s+d[ií]as|buenas\s+tardes|buenas)\b",
    r"\bqui[eé]n\s+eres\b",
    r"\bcon\s+qui[eé]n\s+hablo\b",
    r"\bde\s+parte\s+de\s+qui[eé]n\b",
    r"\bqui[eé]n\s+(llama|es)\b",
]

_NOISE_TOKENS = {
    "[música]",
    "[musica]",
    "[ruido]",
    "[silencio]",
    "[inaudible]",
    "[applause]",
    "...",
    ".",
    "",
}


def _clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    cleaned = raw_text.strip().lower()
    cleaned = re.sub(r"[¿?¡!.,;:\"'()\[\]]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _matches_any(cleaned_text: str, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        if re.search(pattern, cleaned_text, re.IGNORECASE):
            matches.append(pattern)
    return matches


# --- CLASIFICACIÓN DE INTENCIÓN ---

def classify_intent(cleaned_text: str, context: ConversationContext | None = None) -> tuple[CommercialIntent, float, list[str]]:
    """Clasifica el texto del usuario según una jerarquía estricta de seguridad y contexto."""
    # 0. Exclusión activa irrevocable (regla suprema de seguridad)
    if context is not None and context.is_do_not_contact:
        return CommercialIntent.DO_NOT_CONTACT, 1.0, ["dnc_permanent_override"]

    # 1. Petición expresa de NO contacto / baja (máxima prioridad legal y comercial)
    dnc_matches = _matches_any(cleaned_text, _PATTERNS_DO_NOT_CONTACT)
    if dnc_matches:
        return CommercialIntent.DO_NOT_CONTACT, 1.0, dnc_matches

    # 2. Retirada de interés (si en el contexto previo hubo interés o cita y ahora cancela)
    has_prior_interest = context is not None and (context.interest_expressed or context.meeting_requested)
    withdrawal_matches = _matches_any(cleaned_text, _PATTERNS_INTEREST_WITHDRAWAL)
    if withdrawal_matches and (has_prior_interest or re.search(r"\b(ya\s+no|arrepentido|cancela)\b", cleaned_text)):
        return CommercialIntent.INTEREST_WITHDRAWAL, 0.95, withdrawal_matches

    # 3. Transferencia a humano / aclaración de bot
    human_matches = _matches_any(cleaned_text, _PATTERNS_TRANSFER_HUMAN)
    if human_matches:
        return CommercialIntent.TRANSFER_HUMAN, 0.95, human_matches

    # 4. Privacidad y RGPD
    privacy_matches = _matches_any(cleaned_text, _PATTERNS_PRIVACY_INQUIRY)
    if privacy_matches:
        return CommercialIntent.PRIVACY_INQUIRY, 0.95, privacy_matches

    # 5. Ocupado / falta de tiempo
    busy_matches = _matches_any(cleaned_text, _PATTERNS_BUSY_CALL_LATER)
    if busy_matches:
        return CommercialIntent.BUSY_CALL_LATER, 0.90, busy_matches

    # 6. Petición de rellamada específica
    callback_matches = _matches_any(cleaned_text, _PATTERNS_CALLBACK_REQUEST)
    if callback_matches:
        return CommercialIntent.CALLBACK_REQUEST, 0.90, callback_matches

    # 7. Competidor existente
    competitor_matches = _matches_any(cleaned_text, _PATTERNS_EXISTING_COMPETITOR)
    if competitor_matches:
        return CommercialIntent.EXISTING_COMPETITOR, 0.90, competitor_matches

    # 8. Rechazo comercial suave
    rejection_matches = _matches_any(cleaned_text, _PATTERNS_SOFT_REJECTION)
    if rejection_matches:
        return CommercialIntent.SOFT_REJECTION, 0.90, rejection_matches

    # 9. Preguntas de precio / tarifas / presupuesto
    price_matches = _matches_any(cleaned_text, _PATTERNS_PRICE_INQUIRY)
    if price_matches:
        return CommercialIntent.PRICE_INQUIRY, 0.90, price_matches

    # 10. Integraciones técnicas
    tech_matches = _matches_any(cleaned_text, _PATTERNS_TECHNICAL_INTEGRATION)
    if tech_matches:
        return CommercialIntent.TECHNICAL_INTEGRATION, 0.90, tech_matches

    # 11. Disponibilidad de agenda
    sched_matches = _matches_any(cleaned_text, _PATTERNS_SCHEDULE_AVAILABILITY)
    if sched_matches:
        return CommercialIntent.SCHEDULE_AVAILABILITY, 0.90, sched_matches

    # 12. Petición de reunión
    meeting_matches = _matches_any(cleaned_text, _PATTERNS_MEETING_REQUEST)
    if meeting_matches:
        return CommercialIntent.MEETING_REQUEST, 0.95, meeting_matches

    # 13. Expresión de interés / dossier
    interest_matches = _matches_any(cleaned_text, _PATTERNS_EXPRESS_INTEREST)
    if interest_matches:
        return CommercialIntent.EXPRESS_INTEREST, 0.90, interest_matches

    # 14. Información de servicios
    service_matches = _matches_any(cleaned_text, _PATTERNS_SERVICE_INFO)
    if service_matches:
        return CommercialIntent.SERVICE_INFO, 0.90, service_matches

    # 15. Información desconocida de la empresa
    unknown_matches = _matches_any(cleaned_text, _PATTERNS_UNKNOWN_INFO)
    if unknown_matches:
        return CommercialIntent.UNKNOWN_INFO, 0.85, unknown_matches

    # 16. Saludo / presentación
    greeting_matches = _matches_any(cleaned_text, _PATTERNS_GREETING_PRESENTATION)
    if greeting_matches:
        return CommercialIntent.GREETING_PRESENTATION, 0.85, greeting_matches

    # 17. Fallback por defecto
    return CommercialIntent.FALLBACK_CLARIFICATION, 0.50, ["fallback_default"]


# --- GENERACIÓN DE RESPUESTA Y SEGURIDAD COMERCIAL ---

def generate_response_text(intent: CommercialIntent, context: ConversationContext | None = None) -> str:
    """Genera la respuesta comercial garantizando el cumplimiento de las reglas de seguridad."""
    if intent == CommercialIntent.DO_NOT_CONTACT:
        if context is not None and context.is_do_not_contact and context.turn_count > 0:
            return (
                "Su solicitud de no volver a contactar ya fue registrada. "
                "Esta conversación está concluida y sus datos han sido excluidos. "
                "Que tenga un buen día."
            )
        return (
            "Entendido. He registrado inmediatamente su petición de no volver a contactarle "
            "y no recibirá más llamadas ni comunicaciones de nuestra parte. "
            "Disculpe las molestias y que tenga un buen día."
        )

    if intent == CommercialIntent.INTEREST_WITHDRAWAL:
        return (
            "Entendido perfectamente. Tomo nota de que no desea continuar y cancelamos "
            "la solicitud de información. Muchas gracias por su tiempo y que tenga un buen día."
        )

    if intent == CommercialIntent.TRANSFER_HUMAN:
        return (
            "Le informo con total transparencia de que soy un asistente virtual. "
            "Tomo nota de su solicitud para que un asesor comercial de nuestro equipo humano "
            "se ponga en contacto con usted por teléfono o correo lo antes posible."
        )

    if intent == CommercialIntent.PRIVACY_INQUIRY:
        return (
            "Nuestros contactos proceden exclusivamente de fuentes empresariales públicas "
            "y directorios profesionales abiertos, en estricto cumplimiento del RGPD. "
            "Si lo desea, podemos suprimir inmediatamente sus datos o facilitarle nuestra política de privacidad."
        )

    if intent == CommercialIntent.PRICE_INQUIRY:
        return (
            "Nuestras soluciones se adaptan a las necesidades y volumen de cada negocio, "
            "por lo que no disponemos de una tarifa fija estándar. Si lo desea, el equipo comercial "
            "puede evaluar su caso y facilitarle una propuesta a medida sin compromiso."
        )

    if intent == CommercialIntent.BUSY_CALL_LATER:
        return (
            "Entiendo perfectamente que le pille en un mal momento. "
            "¿Prefiere que le contactemos mañana o en alguna otra franja horaria que le venga mejor?"
        )

    if intent == CommercialIntent.CALLBACK_REQUEST:
        return (
            "De acuerdo, tomo nota de su preferencia de horario para que el equipo comercial "
            "intente contactarle en ese momento. Muchas gracias por su tiempo y que tenga un buen día."
        )

    if intent == CommercialIntent.EXISTING_COMPETITOR:
        return (
            "Entendido, es excelente que ya cuenten con una herramienta operativa. "
            "Si en algún momento desean comparar funcionalidades o explorar alternativas de optimización, "
            "quedamos a su entera disposición. Muchas gracias."
        )

    if intent == CommercialIntent.SOFT_REJECTION:
        return (
            "Entendido, muchas gracias por su sinceridad y por atenderme. "
            "Si en el futuro necesitan optimizar sus procesos comerciales, estaremos encantados de ayudarles. "
            "Que tenga un buen día."
        )

    if intent == CommercialIntent.TECHNICAL_INTEGRATION:
        return (
            "Nuestras soluciones están diseñadas para conectarse mediante APIs y servicios estándar "
            "con las principales plataformas del mercado. Para confirmar la compatibilidad exacta con su software específico, "
            "un técnico de nuestro equipo puede revisarlo con usted."
        )

    if intent == CommercialIntent.SCHEDULE_AVAILABILITY:
        return (
            "Como asistente virtual no dispongo de la agenda en tiempo real del equipo. "
            "Indíqueme qué día o franja horaria le vendría bien y se lo trasladaré al equipo comercial "
            "para que le confirmen disponibilidad por correo."
        )

    if intent == CommercialIntent.MEETING_REQUEST:
        return (
            "Con mucho gusto. Tomo nota de su solicitud de reunión. "
            "¿Qué día y franja horaria le vendría mejor, por la mañana o por la tarde? "
            "Nuestro equipo revisará la agenda y le confirmará la cita por correo."
        )

    if intent == CommercialIntent.EXPRESS_INTEREST:
        return (
            "Estupendo. Podemos prepararle un resumen con la información técnica y casos de uso. "
            "¿Podría facilitarme su dirección de correo electrónico para que el equipo comercial se lo envíe?"
        )

    if intent == CommercialIntent.SERVICE_INFO:
        return (
            "Hola, soy el asistente virtual de la empresa. "
            "Desarrollamos soluciones de software para automatizar procesos comerciales y de atención al cliente. "
            "Para orientarle mejor, ¿qué tipo de proceso le gustaría optimizar en su negocio?"
        )

    if intent == CommercialIntent.GREETING_PRESENTATION:
        return (
            "Hola, buenos días. Le habla el asistente virtual de la empresa. "
            "Le contacto para presentarle brevemente cómo optimizamos la gestión comercial de negocios como el suyo. "
            "¿Dispone de un par de minutos?"
        )

    if intent == CommercialIntent.UNKNOWN_INFO:
        return (
            "Disculpe, no dispongo de ese dato específico en este momento. "
            "Tomo nota de su consulta para que nuestro equipo se la aclare por correo si lo desea."
        )

    if intent == CommercialIntent.UNINTELLIGIBLE:
        return (
            "Disculpe, no he podido escucharle con claridad. "
            "¿Podría repetir lo que me decía, por favor?"
        )

    # Fallback por defecto
    return (
        "Gracias por su mensaje. Para poder orientarle adecuadamente, "
        "¿le gustaría conocer nuestros servicios, recibir documentación o coordinar una llamada con nuestro equipo?"
    )


def generate_commercial_response(
    transcribed_text: str,
    context: ConversationContext | None = None,
) -> CommercialResponse:
    """Función de entrada principal que procesa la transcripción, actualiza el estado y emite la respuesta."""
    ctx = context if context is not None else ConversationContext()

    # Manejo de entrada vacía o ininteligible
    if not transcribed_text or not transcribed_text.strip():
        resp_text = generate_response_text(CommercialIntent.UNINTELLIGIBLE, ctx)
        ctx.record_turn(transcribed_text, resp_text, CommercialIntent.UNINTELLIGIBLE)
        return CommercialResponse(
            intent=CommercialIntent.UNINTELLIGIBLE,
            response_text=resp_text,
            confidence=1.0,
            matched_patterns=["empty_input"],
            is_do_not_contact=ctx.is_do_not_contact,
            context=ctx,
        )

    raw_lower = transcribed_text.strip().lower()
    has_letters = any(c.isalnum() for c in raw_lower)
    if raw_lower in _NOISE_TOKENS or not has_letters or len(raw_lower) < 3:
        resp_text = "Disculpe, no he recibido un mensaje claro. ¿Podría indicarme en qué puedo orientarle?"
        ctx.record_turn(transcribed_text, resp_text, CommercialIntent.UNINTELLIGIBLE)
        return CommercialResponse(
            intent=CommercialIntent.UNINTELLIGIBLE,
            response_text=resp_text,
            confidence=0.9,
            matched_patterns=["noise_or_too_short"],
            is_do_not_contact=ctx.is_do_not_contact,
            context=ctx,
        )

    cleaned = _clean_text(transcribed_text)
    intent, confidence, matched_patterns = classify_intent(cleaned, ctx)
    response_text = generate_response_text(intent, ctx)

    ctx.record_turn(transcribed_text, response_text, intent)

    return CommercialResponse(
        intent=intent,
        response_text=response_text,
        confidence=confidence,
        matched_patterns=matched_patterns,
        is_do_not_contact=ctx.is_do_not_contact,
        context=ctx,
    )
