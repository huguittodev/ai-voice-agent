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
    # No volver a llamar / no llamar más / no contactar más / no volver a molestar
    r"\bno\s+(me\s+|nos\s+)?(volv\w*\s+a\s+(llamar|contact\w*|molest\w*)|llam\w*\s+m[aá]s|contact\w*\s+m[aá]s|molest\w*)\b",
    # No me llaméis / no me llames / no contactes
    r"\bno\s+(me\s+|nos\s+)?(llames|llame|llam[eé]is|llamen|contactes|contacte|contacten)\b",
    # Borrad mi/mis/nuestro/nuestros número/contacto/datos/teléfono
    r"\bborr\w*\s+(mi\s+|mis\s+|nuestro\s+|nuestros\s+)?(n[uú]mero|contacto|datos|tel[eé]fono)\b",
    # Dadme / darnos de baja
    r"\b(da[rd]\w*|dar)\s+de\s+baja\b",
    # No quiero que me llaméis / no quiero recibir más llamadas comerciales / no quiero más contacto
    r"\bno\s+quiero\s+(que\s+(me\s+|nos\s+)?llam\w*|recib\w*\s+(m[aá]s\s+)?(llamadas|mensajes|comunicaciones)|m[aá]s\s+(llamadas|contacto|mensajes))\b",
    # Eliminad mi contacto / número / datos de la lista
    r"\belimin\w*\s+((mi\s+|mis\s+|nuestro\s+|nuestros\s+)?(n[uú]mero|contacto|datos|tel[eé]fono)\s+)?de\s+(la|vuestra)\s+lista\b",
    # Lista robinson
    r"\blista\s+robinson\b",
    # No volver a llamar
    r"\bno\s+volv\w*\s+(a\s+)?llamar\b",
]

_PATTERNS_INTEREST_WITHDRAWAL: list[str] = [
    r"\bpens[aá]ndolo\s+bien\s+(ya\s+no|mejor\s+no|lo\s+dejamos)\b",
    r"\bya\s+no\s+(me\s+|nos\s+)?interesa\b",
    r"\bcancel\w*\s+(la\s+)?(cita|reuni[oó]n|solicitud|petici[oó]n|informaci[oó]n|propuesta)\b",
    r"\bolv[ií]da(lo|te)|d[eé]jalo\b",
    r"\bal\s+final\s+(no|nada|lo\s+dejamos)\b",
    r"\bme\s+he\s+arrepentido\b",
]

_PATTERNS_TRANSFER_HUMAN: list[str] = [
    r"\b(p[aá]s\w*|hablar)\s+(con\s+)?(una\s+persona|un\s+humano|alguien\s+real|un\s+operador|un\s+agente\s+humano)\b",
    r"\bp[aá]s\w*\s+con\s+(tu\s+)?(jefe|responsable|superior|encargado)\b",
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
    r"\bpill\w*\s+(muy\s+|bastante\s+)?mal\b",
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


def _remove_accents(text: str) -> str:
    """Normaliza vocales con tilde y diéresis para garantizar coincidencias robustas en español peninsular."""
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }
    for accented, unaccented in replacements.items():
        text = text.replace(accented, unaccented)
    return text


def _clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    cleaned = raw_text.strip().lower()
    cleaned = re.sub(r"[¿?¡!.,;:\"'()\[\]]", " ", cleaned)
    cleaned = _remove_accents(cleaned)
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
    # 0. Exclusión activa irrevocable en la sesión (regla suprema de seguridad)
    if context is not None and context.is_do_not_contact:
        return CommercialIntent.DO_NOT_CONTACT, 1.0, ["dnc_permanent_override"]

    # 1. Petición expresa de NO contacto / baja (máxima prioridad legal y comercial)
    # Proteger contra frases contradictorias como "no quiero dejar de recibir llamadas"
    is_contradictory_dnc = bool(
        re.search(r"\bno\s+quiero\s+dejar\s+de\s+(recibir|tener|admitir)\b", cleaned_text)
    )
    if not is_contradictory_dnc:
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

    # 4. Privacidad y tratamiento de datos
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

    # Si hubo rechazo comercial previo (is_rejected), no reiniciar el discurso de venta ante saludos o mensajes ambiguos
    if context is not None and context.is_rejected:
        return CommercialIntent.SOFT_REJECTION, 0.85, ["post_rejection_no_push"]

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
                "Su solicitud de no contacto ya quedó registrada en esta sesión y no volveremos a contactarle. "
                "Esta conversación está concluida. Que tenga un buen día."
            )
        return (
            "Entendido. He registrado en esta sesión su petición de no volver a contactarle "
            "y no continuaremos la llamada. Disculpe las molestias y que tenga un buen día."
        )

    if intent == CommercialIntent.INTEREST_WITHDRAWAL:
        return (
            "Entendido perfectamente. Tomo nota en esta sesión de que prefiere no continuar "
            "y cancelamos la propuesta. Muchas gracias por su tiempo y que tenga un buen día."
        )

    if intent == CommercialIntent.TRANSFER_HUMAN:
        return (
            "Le informo con total transparencia de que soy un asistente virtual en pruebas. "
            "Actualmente este prototipo no dispone de transferencia directa con agentes humanos, "
            "pero puedo registrar su solicitud para cuando el canal humano esté disponible."
        )

    if intent == CommercialIntent.PRIVACY_INQUIRY:
        return (
            "Esta llamada forma parte de una prueba técnica de un prototipo local con datos de prueba. "
            "Si prefiere no participar o no recibir comunicaciones de prueba, indíquelo y registraremos su exclusión de inmediato."
        )

    if intent == CommercialIntent.PRICE_INQUIRY:
        return (
            "Al tratarse de un prototipo experimental local, no disponemos de una tarifa fija estándar ni planes de precios cerrados. "
            "Cualquier propuesta económica deberá definirse en fases posteriores del proyecto."
        )

    if intent == CommercialIntent.BUSY_CALL_LATER:
        return (
            "Entiendo perfectamente que le pille en un mal momento. "
            "¿Prefiere que intentemos contactarle mañana o en alguna otra franja horaria que le venga mejor?"
        )

    if intent == CommercialIntent.CALLBACK_REQUEST:
        return (
            "De acuerdo, tomo nota de su preferencia de horario en esta simulación. "
            "Muchas gracias por su atención y que tenga un buen día."
        )

    if intent == CommercialIntent.EXISTING_COMPETITOR:
        return (
            "Entendido, es una excelente referencia que ya cuenten con una solución operativa. "
            "Agradezco que nos lo indique para no interferir en su operativa actual. Muchas gracias."
        )

    if intent == CommercialIntent.SOFT_REJECTION:
        if context is not None and context.is_rejected and context.turn_count > 0:
            return (
                "Entendido. Como le comentaba, respetamos su decisión de no continuar con la propuesta. "
                "Quedamos a su disposición si en el futuro necesita consultar algo. Que tenga un buen día."
            )
        return (
            "Entendido, muchas gracias por su sinceridad y por atenderme. "
            "Respetamos su respuesta y no insistiremos con más información. Que tenga un buen día."
        )

    if intent == CommercialIntent.TECHNICAL_INTEGRATION:
        return (
            "Este prototipo se encuentra actualmente en fase de validación de voz y no dispone de integraciones "
            "ni APIs activas con software de terceros. Cualquier requerimiento técnico debe ser evaluado con los responsables del proyecto."
        )

    if intent == CommercialIntent.SCHEDULE_AVAILABILITY:
        return (
            "Como asistente virtual en pruebas no dispongo de agenda en tiempo real del equipo. "
            "Indíqueme qué día o franja le convendría y la anotaremos como propuesta orientativa."
        )

    if intent == CommercialIntent.MEETING_REQUEST:
        return (
            "Con mucho gusto. Tomo nota de su propuesta de reunión como una solicitud pendiente. "
            "¿Qué día y franja horaria le vendría mejor, por la mañana o por la tarde? "
            "El equipo responsable revisará la agenda y le confirmará la disponibilidad, ya que esta anotación queda como propuesta y no como cita fijada."
        )

    if intent == CommercialIntent.EXPRESS_INTEREST:
        return (
            "Estupendo, agradezco su interés. Al tratarse de un prototipo en pruebas, "
            "¿podría facilitarme su dirección de correo electrónico para coordinar el envío de información en cuanto esté disponible?"
        )

    if intent == CommercialIntent.SERVICE_INFO:
        return (
            "Hola, soy el asistente virtual en fase de prueba técnica. "
            "El objetivo del proyecto es investigar la automatización de procesos de atención y consulta comercial por voz. "
            "Para orientarle mejor, ¿qué tipo de proceso le interesaría consultar?"
        )

    if intent == CommercialIntent.GREETING_PRESENTATION:
        return (
            "Hola, buenos días. Le habla el asistente virtual en fase de prueba técnica. "
            "Le contacto para comprobar el funcionamiento de nuestro sistema de diálogo por voz. "
            "¿Dispone de un par de minutos?"
        )

    if intent == CommercialIntent.UNKNOWN_INFO:
        return (
            "Disculpe, no dispongo de ese dato específico en este prototipo. "
            "Tomo nota de su consulta para trasladarla en la revisión técnica del sistema."
        )

    if intent == CommercialIntent.UNINTELLIGIBLE:
        return (
            "Disculpe, no he podido escucharle con claridad. "
            "¿Podría repetir lo que me decía, por favor?"
        )

    # Fallback por defecto
    return (
        "Gracias por su mensaje. Para poder orientarle en esta prueba técnica, "
        "¿le gustaría conocer nuestros servicios o el propósito del prototipo, sugerir un horario o prefiere no continuar?"
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
