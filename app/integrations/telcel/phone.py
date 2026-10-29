"""
integrations/telcel/phone.py

Normalización de números telefónicos al formato que piden las APIs Telcel.
"""


def to_msisdn(phone_number: str) -> str:
    """Normaliza a MSISDN de 10 dígitos (sin lada país).

    Entradas soportadas:
      - "521XXXXXXXXXX" (formato WhatsApp, 13 dígitos con el "1" de celular MX) -> se quita "521"
      - "52XXXXXXXXXX"  (12 dígitos, con lada país) -> se quita "52"
      - "XXXXXXXXXX"    (10 dígitos) -> se deja igual
    """
    n = (phone_number or "").strip().lstrip("+")
    if n.startswith("521") and len(n) == 13:
        return n[3:]
    if n.startswith("52") and len(n) == 12:
        return n[2:]
    return n
