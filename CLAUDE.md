# CLAUDE.md — ReniAgent Strands Nativo

Contexto completo para Claude Code. Lee este archivo antes de tocar cualquier código.

---

## ¿Qué es este proyecto?

Agente de ventas Telcel migrado de **LangGraph** a **Strands Agents** con arquitectura nativa.
Atiende clientes por WhatsApp para ofrecerles migración a planes vigentes (Telcel Libre / Ultra).

**Principios de arquitectura:**
- No hay router, no hay nodos, no hay clasificación explícita de intenciones
- El catálogo de planes está inyectado en el system prompt — el modelo razona directamente
- Solo UNA herramienta Strands: `iniciar_contratacion`
- El flujo de contratación (CONTRACT) es 100% determinístico — sin LLM
- Persistencia de sesión en PostgreSQL por número de teléfono

---

## Setup rápido

```bash
# 1. Activar entorno virtual
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

# 2. Instalar dependencias
pip install strands-agents litellm fastapi uvicorn python-dotenv oci sqlalchemy psycopg2-binary

# 3. Configurar .env
copy .env.example .env
# Editar .env con credenciales OCI y PostgreSQL

# 4. Correr el servidor
python -m uvicorn main:app --reload

# 5. CLI para pruebas locales
python scripts/test_agent.py
```

### Variables de entorno requeridas (`.env`)

```env
OCI_MODEL_ID=meta.llama-3.3-70b-instruct
OCI_SERVICE_ENDPOINT=https://inference.generativeai.us-chicago-1.oci.oraclecloud.com
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxxx
OCI_REGION=us-chicago-1
OCI_USER=ocid1.user.oc1..xxxxx
OCI_TENANCY=ocid1.tenancy.oc1..xxxxx
OCI_FINGERPRINT=xx:xx:xx:xx:xx:xx
OCI_KEY_FILE=./.oci/oci_api_key.pem
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=600
API_KEY=tu-api-key
DATABASE_URL=postgresql://postgres:oracle@localhost:5432/reni_agent
SESSION_TTL_HOURS=24
```

---

## Arquitectura de archivos

```
agenteTelcel/
├── main.py                          ← FastAPI entry point con persistencia PostgreSQL
├── scripts/
│   └── test_agent.py               ← CLI de pruebas (/select, /list, /reset)
├── docs/
│   └── Masivo_clientes.csv         ← Perfiles de clientes para pruebas
├── app/
│   ├── agent/
│   │   └── reni_agent.py           ← Orquestador principal (LLM + CONTRACT)
│   ├── catalog/
│   │   └── plans.py                ← Catálogo completo — FUENTE DE VERDAD
│   ├── config/
│   │   └── oci_model.py            ← Modelo OCI via LiteLLM + parche stream_options
│   ├── contract/
│   │   ├── contract_flow.py        ← Flujo OTP determinístico (sin LLM)
│   │   └── post_sale.py            ← Template de confirmación con folio
│   ├── prompts/
│   │   ├── general_rules.py        ← Reglas fijas del agente (todas las reglas de negocio)
│   │   ├── system_prompt.py        ← Contexto dinámico + catálogo inyectado
│   │   └── campaign_template.py    ← Mensaje inicial determinístico (sin LLM)
│   ├── state/
│   │   ├── session.py              ← SessionState (datos del cliente + flags de contrato)
│   │   ├── persistence.py          ← PostgreSQL CRUD (load/save/delete session)
│   │   └── serializer.py           ← SessionState ↔ dict para PostgreSQL
│   └── tools/
│       ├── telcel_tools.py         ← UNA sola herramienta: iniciar_contratacion
│       └── prospect_loader.py      ← Carga CSV para CLI
```

---

## Flujo de un turno

```
Cliente envía mensaje
    │
    ▼
run_turn() en reni_agent.py
    │
    ├── session.stage == "CONTRACT"?
    │       ├── Sí → handle_contract_turn() [DETERMINÍSTICO, sin LLM]
    │       │       ├── authentication_locked → mensaje bloqueo + stage=END
    │       │       ├── awaiting_otp → validar T12345 (OTP fijo para pruebas)
    │       │       ├── awaiting_contract_confirmation → validar ACEPTO/CONFIRMO
    │       │       └── primer ingreso → build_summary_template()
    │       └── No → flujo LLM
    │
    ├── LLM con system_prompt + herramienta iniciar_contratacion
    │       ├── Si LLM invoca iniciar_contratacion → interceptar → handle_contract_turn()
    │       └── Si LLM responde texto → clean_response() → retornar
    │
    └── Guardar historial en PostgreSQL
```

---

## El catálogo en el system prompt

El catálogo completo va inyectado en `system_prompt.py` via `build_catalog_block()`.
El modelo NO necesita herramientas para consultar precios, GB ni beneficios.

El bloque incluye:
- Planes elegibles (precio >= renta actual) en modalidad del cliente
- Plan informativo más barato (solo si existe uno más barato)
- Precios en modalidad alternativa (para no inventarlos cuando el cliente pregunte)
- Nota de promoción si aplica

**NUNCA agregar datos de planes hardcodeados en el prompt** — siempre usar `plans.py`.

---

## Flujo de contratación (contract_flow.py)

```
Cliente dice "sí" / "acepto" / "me interesa"
    ↓
LLM invoca iniciar_contratacion(plan_id)
    ↓
reni_agent intercepta → handle_contract_turn() → build_summary_template()
    ↓
Cliente responde ACEPTO o CONFIRMO
    ↓
handle_contract_turn() → envía OTP → "ingrese código de SMS"
    ↓
Cliente ingresa T12345 (OTP fijo para pruebas)
    ↓
OTP válido → genera folio TC-XXXXXXXX → stage = POST_SALE
    ↓
build_post_sale_message() → mensaje de confirmación con folio
    ↓
stage = END
```

**Casos especiales:**
- OTP incorrecto → máx 3 intentos → bloqueo
- Afirmación vaga (sí, ok, dale) → pedir ACEPTO/CONFIRMO explícito
- Cliente cancela (NO) → volver a PERSUASION
- Pregunta durante espera OTP → LLM responde y recuerda el código pendiente

---

## La única herramienta Strands

`iniciar_contratacion(plan_id)` en `telcel_tools.py`:
- Valida que el plan existe en el catálogo
- Valida que el precio es >= renta actual
- Actualiza `session.plan_selected` y `session.stage = "CONTRACT"`
- El resultado lo intercepta `reni_agent.py` para iniciar el flujo determinístico

**NUNCA agregar más herramientas** a menos que sea una acción real que modifique estado.
Las consultas de catálogo van en el system prompt, no en herramientas.

---

## Reglas de negocio críticas

1. **Modalidad fija** — mismo Controlado/Abierto que el plan actual. Cambio → CAC
2. **No activar por debajo de renta** — planes más baratos son informativos, no activables aquí
3. **Familia Libre como recomendación** — recommend_plan() filtra solo Telcel Libre
4. **Promoción de GB** — solo aplica cuando precio nuevo > precio actual + $1
5. **Apps ilimitadas Telcel Libre** — exactamente: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber. YouTube, TikTok y cualquier otra NO están incluidas
6. **OTP fijo para pruebas** — T12345 (cambiar por servicio real en producción)
7. **Trato de usted** — siempre, sin excepción
8. **Modalidad en nombre del plan** — siempre "Telcel Libre 2 Controlado", nunca solo "Telcel Libre 2"

---

## Problema conocido — tool calling con Llama en OCI

Llama 3.3 en OCI a veces escribe el nombre de la herramienta como texto literal
en lugar de invocarla. `reni_agent.py` tiene dos safety nets:

1. **Regex pattern** — detecta `[tool_name]` o `tool_name(param)` y reintenta
2. **Intercepción de iniciar_contratacion** — si el LLM la invocó correctamente,
   `reni_agent.py` ignora la respuesta del LLM y usa el flujo determinístico

---

## Parche OCI stream_options

En `app/config/oci_model.py` hay un parche en memoria que fuerza `drop_params=True`
para que LiteLLM ignore el parámetro `stream_options` que OCI no soporta:

```python
from litellm.llms.oci.chat.transformation import OCIChatConfig
_original_map = OCIChatConfig.map_openai_params
def _patched_map(self, non_default_params, optional_params, model, drop_params):
    return _original_map(self, non_default_params, optional_params, model, drop_params=True)
OCIChatConfig.map_openai_params = _patched_map
```

Eliminar cuando LiteLLM corrija esto oficialmente.

---

## Comandos CLI (test_agent.py)

```
/list          → lista los 18 perfiles del CSV
/select N      → carga perfil N, genera mensaje de campaña y espera respuesta
/reset         → limpia sesión local y elimina de PostgreSQL
/perfil        → muestra datos del cliente activo
/exit          → salir
```

El CLI no usa PostgreSQL para el historial — solo para /reset.
El API (/chat endpoint) sí usa PostgreSQL en cada turno.

---

## Fases completadas y pendientes

- [x] **Fase 1** — Base: OCI, identidad, reglas generales, FastAPI
- [x] **Fase 2** — Arquitectura nativa: catálogo en prompt, herramienta única
- [x] **Fase 3** — Contratación: OTP, validación, folio, post-sale
- [x] **Fase 4** — Persistencia: PostgreSQL por número de teléfono
- [ ] **Fase 5** — OTP real: integrar servicio SMS real (reemplazar T12345)
- [ ] **Fase 6** — Integración WhatsApp: webhook Meta, envío/recepción
- [ ] **Fase 7** — Logs/métricas: auditoría de conversaciones y tasa de conversión
- [ ] **Fase 8** — Seguridad: ARCO, tokenización PII

---

## Cómo agregar nueva funcionalidad

**Nueva regla de negocio** → `app/prompts/general_rules.py`
**Nuevo dato contextual del cliente** → `app/prompts/system_prompt.py`
**Nuevo dato del plan** → `app/catalog/plans.py`
**Nueva acción que modifica estado** → nueva herramienta en `app/tools/telcel_tools.py`
**Nuevo paso en el flujo de contrato** → `app/contract/contract_flow.py`

**NUNCA** agregar herramientas para consultas — van en el system prompt.
**NUNCA** hardcodear precios o GB fuera de `plans.py`.
