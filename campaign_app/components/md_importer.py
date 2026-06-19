"""
Parse a Markdown file of FAQs into a list of dicts ready for bulk_create_preguntas.

Supports two formats:

─── Simple format ───────────────────────────────────────────────────
    ## Sección (se usa como ambito)

    **¿Pregunta aquí?**
    Respuesta aquí, puede ser multilínea.

─── FAQ format (preguntas_frecuentes_planes.md) ─────────────────────
    ## FAQ N: ¿Pregunta aquí?

    **Respuesta:**
    Cuerpo de la respuesta, puede ser multilínea.

    **Límites:**          ← se descarta (instrucción interna)
    Texto de límites...

    **Cómo usar esta respuesta (instrucción para el agente):**  ← también se descarta
    ...

Key rule: a heading `## FAQ N: texto` sets the *question* (not the ambito) and activates
FAQ mode for that entry. In FAQ mode a subsequent bold line is treated as formatted
content inside the answer, NOT as a new question — unless it's a section marker
(**Respuesta:**, **Límites:**, etc.). In simple mode, any bold line starts a new Q.
"""

import re
import unicodedata
from typing import Optional


def _norm(s: str) -> str:
    """Lowercase + strip accents + strip trailing colon/space."""
    s = s.lower().rstrip(":").strip()
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


_RESPUESTA_MARKERS = {"respuesta", "answer"}
_SKIP_MARKERS = {"limites", "limite", "notas", "nota"}
_SKIP_PREFIXES = ("como usar", "instruccion", "instrucciones")


def _is_respuesta_marker(text: str) -> bool:
    return _norm(text) in _RESPUESTA_MARKERS


def _is_skip_marker(text: str) -> bool:
    n = _norm(text)
    return n in _SKIP_MARKERS or any(n.startswith(p) for p in _SKIP_PREFIXES)


def parse_faq_md(text: str,
                 beneficio_id: Optional[int] = None,
                 servicio_id: Optional[int] = None) -> list[dict]:
    """
    Parse FAQ markdown text and return a list of dicts:
      {pregunta, respuesta, ambito, beneficio_id, servicio_id}
    """
    items: list[dict] = []
    current_ambito = "general"
    current_pregunta: Optional[str] = None
    current_respuesta_lines: list[str] = []
    faq_mode = False   # True when the question came from a "## FAQ N:" heading
    in_skip = False    # True while inside **Límites:** / **Cómo usar…** section

    def _flush():
        if current_pregunta and current_respuesta_lines:
            items.append({
                "pregunta": current_pregunta,
                "respuesta": "\n".join(current_respuesta_lines).strip(),
                "ambito": current_ambito,
                "beneficio_id": beneficio_id,
                "servicio_id": servicio_id,
            })

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # ── Heading ───────────────────────────────────────────────────────────
        heading_match = re.match(r"^#{2,3}\s+(.+)$", line)
        if heading_match:
            _flush()
            current_pregunta = None
            current_respuesta_lines = []
            faq_mode = False
            in_skip = False

            heading_text = heading_match.group(1).strip()

            faq_match = re.match(r"^FAQ\s+\d+:\s*(.+)$", heading_text, re.IGNORECASE)
            if faq_match:
                # FAQ format: heading IS the question
                current_pregunta = faq_match.group(1).strip()
                faq_mode = True
                # ambito stays as previously set (or "general")
            else:
                # Simple format: heading sets the ambito
                current_ambito = heading_text.lower()

            continue

        # ── Bold line ─────────────────────────────────────────────────────────
        bold_match = re.match(r"^\*\*(.+?)\*\*\s*$", line)
        if bold_match:
            bold_text = bold_match.group(1).strip()

            # Special section markers — never treat as question or answer
            if _is_respuesta_marker(bold_text):
                in_skip = False   # entering answer body
                continue

            if _is_skip_marker(bold_text):
                in_skip = True
                continue

            # Regular bold line
            if faq_mode:
                # Inside a FAQ entry: treat as formatted bold within the answer
                if not in_skip:
                    current_respuesta_lines.append(raw_line.strip())
            else:
                # Simple format: bold line = new question
                _flush()
                current_pregunta = bold_text
                current_respuesta_lines = []
                in_skip = False

            continue

        # ── Empty line ────────────────────────────────────────────────────────
        if not line:
            continue

        # ── Content line ──────────────────────────────────────────────────────
        if in_skip:
            continue

        if current_pregunta is not None:
            current_respuesta_lines.append(line)

    _flush()
    return items


def parse_faq_file(path: str,
                   beneficio_id: Optional[int] = None,
                   servicio_id: Optional[int] = None) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return parse_faq_md(f.read(), beneficio_id=beneficio_id,
                             servicio_id=servicio_id)
