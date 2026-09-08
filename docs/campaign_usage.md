# Campaign App — Uso en desarrollo

Guía para lanzar campañas de WhatsApp desde entorno local.

---

## Flujo rápido (3 pasos)

### Paso 1 — Abrir el túnel SSH

Abre una terminal, ejecuta esto y **déjala abierta** durante toda la sesión:

```powershell
ssh -i ssh-key-2026-06-23-pgsql.key -N -L 5433:172.16.5.109:5432 pgsqltunnel@129.153.143.19
```

La terminal queda en silencio — eso es normal. Si pide confirmar el host escribe `yes`.

### Paso 2 — Configurar el `.env`

Asegúrate de que tu `.env` tenga esta línea apuntando al túnel:

```env
DATABASE_URL=postgresql://pgadmin:Or4%23D3Sytem-@localhost:5433/reni_agent
```

### Paso 3 — Enviar la campaña

Con el túnel activo, ejecuta en otra terminal:

```powershell
python scripts/send_campaign.py
```

Comandos disponibles:

```
/list        — lista todos los clientes del CSV
/select N    — previsualiza el perfil del cliente N
/send N      — envía el template al cliente N
/send all    — envía a todos (pide confirmación)
/exit        — salir
```

Cuando el cliente contesta el template, el agente en OCI responde automáticamente.

---

## Streamlit (requiere rebuild del pod)

> **Estado actual**: el pod OCI aún no incluye `campaign_app` — el dispatch desde Streamlit da error 503.
> Mientras el equipo reconstruye la imagen, usar el script del Paso 3.

Una vez reconstruida la imagen, los pasos son:

### Paso 1 — Abrir el túnel SSH (igual que antes)

```powershell
ssh -i ssh-key-2026-06-23-pgsql.key -N -L 5433:172.16.5.109:5432 pgsqltunnel@129.153.143.19
```

### Paso 2 — Verificar el `.env`

Asegúrate de tener estas variables además de `DATABASE_URL`:

```env
DATABASE_URL=postgresql://pgadmin:Or4%23D3Sytem-@localhost:5433/reni_agent
CAMPAIGN_API_BASE=https://gsycay4fqacuc7eiloj4f55mam.apigateway.us-ashburn-1.oci.customer-oci.com/telcelstrands
CAMPAIGN_API_KEY=zvDQevdVVrijrczOGUc4fRJ0ZC6h-yHfF7ZZgsK8hZY
WHATSAPP_APP_SECRET=f6511b800742ca9e4389d749b54a1293
```

### Paso 3 — Ejecutar Streamlit

```powershell
cd campaign_app
streamlit run Home.py
```

Se abre el navegador en `http://localhost:8501`. Desde ahí se crean campañas, se importan clientes y se lanza el dispatch.

---

## Primera vez — inicializar la BD de OCI

Solo necesario si la BD aún no tiene las tablas de campaña:

```powershell
# Crear tablas
python -c "
import sys, os; sys.path.insert(0, '.')
from sqlalchemy import create_engine
from campaign_app.db.models import Base
engine = create_engine('postgresql://pgadmin:Or4%23D3Sytem-@localhost:5433/reni_agent')
Base.metadata.create_all(engine)
print('Tablas creadas')
"

# Poblar catálogo
python campaign_app/db/seed.py
```

El seed es idempotente — se puede ejecutar varias veces sin duplicar datos.

---

## Notas sobre templates de WhatsApp

A partir de las plantillas reaprobadas en Meta (`template_telcel_libre` / `template_telcel_ultra`),
los nombres ya NO están cruzados — cada variable de entorno apunta al template del mismo nombre:

```env
TEMPLATE_LIBRE=template_telcel_libre
TEMPLATE_ULTRA=template_telcel_ultra
```

Estas plantillas nuevas tienen menos variables que las anteriores — "Abierto" y la frase de
introducción ("Con este plan obtendrá...") quedaron fijas en el cuerpo aprobado, ya no son `{{N}}`:

- `template_telcel_libre` — 5 variables: nombre, plan (sin modalidad), precio, GB, cashback
- `template_telcel_ultra` — 4 variables: nombre, plan (sin modalidad), precio, GB

El payload enviado a Meta incluye siempre `header` (estático) + `body` (con variables `{{1}}`, `{{2}}`...).
No incluir componente `button` si el template aprobado no tiene botones — Meta devuelve error 132018.

---

## Arquitectura de red

```
Tu máquina
  ├── Túnel SSH          → 129.153.143.19 → 172.16.5.109:5432 (BD OCI)
  ├── send_campaign.py   → WhatsApp API directamente + BD OCI vía túnel
  └── Streamlit          → BD OCI vía túnel + pod OCI vía API Gateway

OCI (producción)
  ├── API Gateway        → https://gsycay4f....apigateway.us-ashburn-1.oci...
  ├── Pod FastAPI        → recibe webhooks y responde conversaciones
  └── PostgreSQL         → 172.16.5.109:5432 (privado)
```

---

## Pendiente

- [ ] Rebuild de imagen Docker con `COPY campaign_app/ ./campaign_app/` — habilita Streamlit dispatch
- [ ] Exponer rutas `/campaign` y `/campaign/dispatch` en el API Gateway de OCI
