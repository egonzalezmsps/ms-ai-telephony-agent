from components.md_importer import parse_faq_md


# ── Formato simple ────────────────────────────────────────────────────────────

MD_SAMPLE = """
## Apps ilimitadas

**¿Qué apps incluye el plan Libre?**
Facebook, WhatsApp, Messenger, X, Instagram, Snapchat y Uber.

**¿TikTok está incluido?**
No, TikTok no forma parte de las apps ilimitadas.

## Cashback

**¿Cómo funciona el cashback?**
Se acredita mensualmente en tu cuenta.
Puedes usarlo para pagar tu factura.
"""

MD_NO_HEADING = """
**¿Cuánto cuesta?**
Consulta el catálogo de planes.
"""

MD_MULTILINE_ANSWER = """
## general

**¿Qué es Claro Drive?**
Es almacenamiento en la nube.
Incluye 20 GB de espacio.
Disponible en iOS y Android.
"""

# ── Formato FAQ (preguntas_frecuentes_planes.md) ──────────────────────────────

MD_FAQ_FORMAT = """
## FAQ 1: ¿Qué es el cashback?

**Respuesta:**
El cashback es un beneficio mensual exclusivo de Telcel Libre.
Se abona automáticamente en tu factura.

**Límites:**
No aplica a planes Ultra.

## FAQ 2: ¿Es acumulable el cashback?

**Respuesta:**
No. El cashback es no acumulable y no transferible.

**Cómo usar esta respuesta (instrucción para el agente):**
Dar la respuesta una sola vez.
"""

MD_FAQ_WITH_BOLD_IN_ANSWER = """
## FAQ 3: ¿Qué puedo hacer con el cashback?

**Respuesta:**
Puedes usarlo en:

- **Más Datos:** paquetes adicionales de GB.
- **Internet por Tiempo:** acceso por horas.

**Límites:**
No inventar usos no documentados.
"""

MD_FAQ_LIMITES_VARIANT = """
## FAQ 4: ¿Qué pasa si genero excedentes?

**Respuesta:**
El cashback no se puede redimir si tienes excedentes activos.

**Notas:**
Solo mencionar esto si el cliente lo pregunta.
"""


# ── Tests: formato simple (regresión) ─────────────────────────────────────────

def test_parse_basic_sections():
    items = parse_faq_md(MD_SAMPLE)
    assert len(items) == 3


def test_ambito_from_heading():
    items = parse_faq_md(MD_SAMPLE)
    assert items[0]["ambito"] == "apps ilimitadas"
    assert items[2]["ambito"] == "cashback"


def test_pregunta_content():
    items = parse_faq_md(MD_SAMPLE)
    assert items[0]["pregunta"] == "¿Qué apps incluye el plan Libre?"


def test_respuesta_content():
    items = parse_faq_md(MD_SAMPLE)
    assert "Facebook" in items[0]["respuesta"]
    assert "TikTok" not in items[0]["respuesta"]


def test_multiline_answer_joined():
    items = parse_faq_md(MD_MULTILINE_ANSWER)
    assert len(items) == 1
    assert "20 GB" in items[0]["respuesta"]
    assert "iOS" in items[0]["respuesta"]


def test_no_heading_defaults_to_general():
    items = parse_faq_md(MD_NO_HEADING)
    assert len(items) == 1
    assert items[0]["ambito"] == "general"


def test_beneficio_id_passed_through():
    items = parse_faq_md(MD_SAMPLE, beneficio_id=42)
    assert all(i["beneficio_id"] == 42 for i in items)
    assert all(i["servicio_id"] is None for i in items)


def test_servicio_id_passed_through():
    items = parse_faq_md(MD_SAMPLE, servicio_id=7)
    assert all(i["servicio_id"] == 7 for i in items)


def test_empty_md_returns_empty_list():
    assert parse_faq_md("") == []


def test_heading_only_no_questions_returns_empty():
    assert parse_faq_md("## Solo un título\n") == []


# ── Tests: formato FAQ ────────────────────────────────────────────────────────

def test_faq_format_extracts_two_items():
    items = parse_faq_md(MD_FAQ_FORMAT)
    assert len(items) == 2


def test_faq_format_pregunta_from_heading():
    items = parse_faq_md(MD_FAQ_FORMAT)
    assert items[0]["pregunta"] == "¿Qué es el cashback?"
    assert items[1]["pregunta"] == "¿Es acumulable el cashback?"


def test_faq_format_respuesta_body_included():
    items = parse_faq_md(MD_FAQ_FORMAT)
    assert "beneficio mensual" in items[0]["respuesta"]
    assert "abona automáticamente" in items[0]["respuesta"]


def test_faq_format_limites_excluded_from_respuesta():
    items = parse_faq_md(MD_FAQ_FORMAT)
    # "Límites:" content must not appear in the answer
    assert "No aplica a planes Ultra" not in items[0]["respuesta"]


def test_faq_format_como_usar_excluded():
    items = parse_faq_md(MD_FAQ_FORMAT)
    assert "Dar la respuesta una sola vez" not in items[1]["respuesta"]


def test_faq_format_respuesta_is_not_a_question():
    items = parse_faq_md(MD_FAQ_FORMAT)
    # "Respuesta" must never appear as a pregunta
    for item in items:
        assert item["pregunta"].lower() not in ("respuesta", "respuesta:")


def test_faq_format_bold_in_answer_kept():
    items = parse_faq_md(MD_FAQ_WITH_BOLD_IN_ANSWER)
    assert len(items) == 1
    assert "Más Datos" in items[0]["respuesta"]
    assert "Internet por Tiempo" in items[0]["respuesta"]


def test_faq_format_limites_excluded_from_bold_answer():
    items = parse_faq_md(MD_FAQ_WITH_BOLD_IN_ANSWER)
    assert "No inventar usos" not in items[0]["respuesta"]


def test_faq_format_notas_variant_excluded():
    items = parse_faq_md(MD_FAQ_LIMITES_VARIANT)
    assert len(items) == 1
    assert "Solo mencionar esto" not in items[0]["respuesta"]
    assert "excedentes activos" in items[0]["respuesta"]
