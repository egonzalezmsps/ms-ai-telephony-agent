"""
scripts/seed_campaign_clientes.py

Puebla las 3 tablas de campaign_app necesarias para disparar
POST /campaign/dispatch contra clientes reales: Campana, Cliente y
CampanaCliente (la tabla puente que permite rastrear el resultado después).

No modifica el esquema de campaign_app — solo llena los campos mínimos que
usa /campaign/dispatch (linea, nombre, apellidos, plan_actual_nombre,
tipo_suscripcion, renta_plan). El resto de columnas de Cliente queda en NULL.

Fuente de datos: docs/Masivo_clientes.csv (ya recortado a las 6 columnas
obligatorias), vía app.tools.prospect_loader.load_prospects().

Idempotente: si la campaña, el cliente o la fila puente ya existen, no los
duplica — solo informa cuántos ya existían.

Uso:
    python scripts/seed_campaign_clientes.py ["Nombre de la campaña"] [--linea NUMERO]

    --linea NUMERO   Si se especifica, solo siembra ese cliente (en vez de
                     todo el CSV) — útil para pruebas individuales antes de
                     un envío masivo.

Al final imprime el campana_id y el body JSON listo para POST /campaign/dispatch.
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.tools.prospect_loader import load_prospects, MODALITY_MAP

DEFAULT_CAMPANA_NOMBRE = "Migracion Telcel Libre"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nombre_campana", nargs="?", default=DEFAULT_CAMPANA_NOMBRE)
    parser.add_argument("--linea", help="Solo sembrar este cliente (en vez de todo el CSV)")
    args = parser.parse_args()
    nombre_campana = args.nombre_campana

    from campaign_app.db.database import get_db, get_engine
    from campaign_app.db.models import Base, Cliente, Campana, CampanaCliente

    Base.metadata.create_all(get_engine())

    rows = load_prospects()
    if args.linea:
        rows = [r for r in rows if str(r.get("linea", "")).strip() == args.linea.strip()]
        if not rows:
            print(f"No se encontró la línea '{args.linea}' en el CSV.")
            return

    if not rows:
        print("No se encontraron clientes en el CSV.")
        return

    clientes_creados = clientes_existentes = 0
    puentes_creados = puentes_existentes = 0

    with get_db() as db:
        campana = db.query(Campana).filter_by(nombre=nombre_campana).first()
        if campana:
            print(f"Campaña ya existente: '{nombre_campana}' (id={campana.id})")
        else:
            campana = Campana(nombre=nombre_campana, estado="activa")
            db.add(campana)
            db.flush()
            print(f"Campaña creada: '{nombre_campana}' (id={campana.id})")
        campana_id = campana.id

        for row in rows:
            linea = str(row.get("linea", "")).strip()
            if not linea:
                continue

            cliente = db.query(Cliente).filter_by(linea=linea).first()
            if cliente:
                clientes_existentes += 1
            else:
                modalidad = MODALITY_MAP.get(row.get("tiposuscripcion", "POSTPAGO"), "Abierto")
                db.add(Cliente(
                    linea=linea,
                    nombre=row.get("nombre", "").strip(),
                    apellidos=row.get("apellidos", "").strip(),
                    plan_actual_nombre=row.get("plan", "").strip().title(),
                    tipo_suscripcion=modalidad,
                    renta_plan=float(row.get("rentaplan") or 0),
                ))
                clientes_creados += 1

            puente = db.query(CampanaCliente).filter_by(campana_id=campana_id, linea=linea).first()
            if puente:
                puentes_existentes += 1
            else:
                db.add(CampanaCliente(campana_id=campana_id, linea=linea, estado_envio="pendiente"))
                puentes_creados += 1

    print(f"\nClientes: {clientes_creados} creados, {clientes_existentes} ya existían")
    print(f"CampanaCliente: {puentes_creados} creados, {puentes_existentes} ya existían")

    lineas = [str(r.get("linea", "")).strip() for r in rows if r.get("linea")]
    body = {"campana_id": campana_id, "lineas": lineas}
    print(f"\ncampana_id = {campana_id}")
    print("\nBody listo para POST /campaign/dispatch:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
