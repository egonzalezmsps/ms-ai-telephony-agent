"""
scripts/test_dispatch_load.py

Simula un dispatch masivo de 1000 clientes contra POST /campaign/dispatch,
SIN llamar a la API real de WhatsApp (se reemplaza por un stub con latencia
simulada) y SIN necesitar 1000 números reales — se siembran clientes falsos
en la BD (campaign_app), claramente marcados como datos de prueba.

Mide el tiempo total del loop síncrono para estimar si 1000 destinatarios
en una sola petición HTTP corren riesgo de timeout.

Uso:
    python scripts/test_dispatch_load.py [N]   # N = cantidad de clientes, default 1000
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
TEST_PREFIX = "9999900"  # líneas claramente falsas, no reales
CAMPANA_NOMBRE = "TEST_LOAD_SCRIPT"


def seed(n: int):
    from campaign_app.db.database import get_db, get_engine
    from campaign_app.db.models import Base, Cliente, Campana, CampanaCliente

    Base.metadata.create_all(get_engine())

    lineas = [f"{TEST_PREFIX}{i:04d}" for i in range(n)]

    with get_db() as db:
        campana = db.query(Campana).filter_by(nombre=CAMPANA_NOMBRE).first()
        if not campana:
            campana = Campana(nombre=CAMPANA_NOMBRE, estado="activa")
            db.add(campana)
            db.flush()
        campana_id = campana.id

        for linea in lineas:
            if not db.query(Cliente).filter_by(linea=linea).first():
                db.add(Cliente(
                    linea=linea,
                    nombre="Test",
                    apellidos="Load Script",
                    plan_actual_nombre="Telcel Max Sin Limite 1000",
                    tipo_suscripcion="POSTPAGO",
                    renta_plan=229.0,
                ))
            if not db.query(CampanaCliente).filter_by(campana_id=campana_id, linea=linea).first():
                db.add(CampanaCliente(campana_id=campana_id, linea=linea, estado_envio="pendiente"))

    return lineas, campana_id


def cleanup(lineas, campana_id):
    from campaign_app.db.database import get_db
    from campaign_app.db.models import Cliente, Campana, CampanaCliente

    with get_db() as db:
        db.query(CampanaCliente).filter_by(campana_id=campana_id).delete()
        db.query(Cliente).filter(Cliente.linea.in_(lineas)).delete(synchronize_session=False)
        db.query(Campana).filter_by(id=campana_id).delete()


def fake_send_whatsapp_template(to, template_name, params, language_code="es_MX"):
    time.sleep(0.15)  # latencia simulada de una llamada real a Meta Graph API
    return {"contacts": [{"wa_id": to}]}


def fake_send_whatsapp_message(to, message):
    time.sleep(0.15)
    return {"contacts": [{"wa_id": to}]}


def main():
    print(f"Sembrando {N} clientes de prueba (linea {TEST_PREFIX}0000..{TEST_PREFIX}{N-1:04d})...")
    lineas, campana_id = seed(N)

    try:
        import main as bot_main
        from app.routes import campaign as campaign_routes
        campaign_routes.send_whatsapp_template = fake_send_whatsapp_template
        campaign_routes.send_whatsapp_message = fake_send_whatsapp_message

        from fastapi.testclient import TestClient
        client = TestClient(bot_main.app)

        api_key = os.environ.get("API_KEY", "")
        print(f"Disparando POST /campaign/dispatch con {N} lineas (WhatsApp mockeado, ~150ms/llamada)...")

        t0 = time.time()
        resp = client.post(
            "/campaign/dispatch",
            json={"campana_id": campana_id, "lineas": lineas},
            headers={"x-api-key": api_key} if api_key else {},
        )
        elapsed = time.time() - t0

        print(f"\nStatus: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Enviados: {len(data.get('sent', []))}  Fallidos: {len(data.get('failed', []))}")
        else:
            print("Respuesta:", resp.text[:500])

        print(f"\nTiempo total: {elapsed:.1f}s para {N} destinatarios ({elapsed/N*1000:.0f}ms/cliente promedio)")

        for timeout_label, timeout_s in [("nginx default (60s)", 60), ("gunicorn default (30s)", 30), ("ALB default (60s)", 60)]:
            veredicto = "EXCEDE" if elapsed > timeout_s else "OK"
            print(f"  vs {timeout_label}: {veredicto}")
    finally:
        print("\nLimpiando datos de prueba...")
        cleanup(lineas, campana_id)
        print("Listo.")


if __name__ == "__main__":
    main()
