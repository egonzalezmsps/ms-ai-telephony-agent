# CLAUDE.md — ReniAgent Strands Nativo

Contexto completo para Claude Code. Lee este archivo antes de tocar cualquier código.

---

## ¿Qué es este proyecto?

Agente de ventas Telcel migrado de **LangGraph** a **Strands Agents** con arquitectura nativa.
Atiende clientes por WhatsApp para ofrecerles migración a planes vigentes (Telcel Libre / Ultra).

**Principios de arquitectura:**
- No hay nodos ni grafos estilo LangGraph — el flujo vive en `run_turn()` como una secuencia de checks + un único agente LLM
- Clasificación de intenciones vía **router semántico** (`app/router/semantic_router.py`) con embeddings de Cohere en OCI — no es matching de keywords (ver sección de router semántico)
- El catálogo de planes está inyectado en el system prompt — el modelo razona directamente
- Seis herramientas Strands activas (ver sección de herramientas)
- El flujo de contratación (CONTRACT) es 100% determinístico — sin LLM, y se evalúa ANTES del router semántico en cada turno
- Persistencia de sesión en PostgreSQL por número de teléfono
- Detecciones pre-LLM (router semántico + fallbacks de matching exacto) que interceptan y responden sin invocar al modelo

---

## Setup rápido

```bash
# 1. Activar entorno virtual
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux

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

### Tests y scripts de verificación

No hay `pytest` en `requirements.txt`/`uv.lock` — instalarlo aparte (`pip install pytest`) antes de correr lo siguiente:

```bash
# Tests unitarios de campaign_app (crud, md_importer, models)
pytest tests/campaign_app/

# Un solo archivo o test
pytest tests/campaign_app/test_crud.py
pytest tests/campaign_app/test_crud.py::test_nombre_del_test

# Scripts de verificación manual (no son pytest, se corren directo)
python scripts/test_prices.py              # valida precios del catálogo
python scripts/test_all_profiles.py        # corre mensajes de prueba contra los 18 perfiles del CSV
python scripts/test_cross_plans.py         # comparaciones cruzadas de planes entre perfiles
python scripts/test_check_invented_plans.py # prueba _check_invented_plans() de reni_agent.py
python scripts/test_router.py              # prueba directa del router semántico (classify())
python scripts/test_embeddings.py          # exploración directa de la API de embeddings OCI/Cohere
python scripts/list_models.py              # lista modelos disponibles en OCI Generative AI
```

No hay linter ni formatter configurado en el proyecto (sin `ruff`/`black`/`mypy` en `pyproject.toml`).

### Variables de entorno requeridas (`.env`)

```env
# OCI — modelo LLM
OCI_MODEL_ID=meta.llama-3.3-70b-instruct
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxxx
OCI_REGION=us-chicago-1

# OCI auth — API Key (solo si no se usa instance_principal)
# Si OCI_USER no está definido, se usa instance_principal (autenticación automática en OKE)
OCI_USER=ocid1.user.oc1..xxxxx
OCI_TENANCY=ocid1.tenancy.oc1..xxxxx
OCI_FINGERPRINT=xx:xx:xx:xx:xx:xx
OCI_KEY_FILE=./.oci/oci_api_key.pem

# LLM params
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=600

# FastAPI
API_KEY=tu-api-key

# PostgreSQL
DATABASE_URL=postgresql://postgres:oracle@localhost:5432/reni_agent
SESSION_TTL_HOURS=24

# WhatsApp (Meta Cloud API)
VERIFY_TOKEN=tu-verify-token-whatsapp
WHATSAPP_ACCESS_TOKEN=tu-token-meta
WHATSAPP_PHONE_NUMBER_ID=tu-phone-id-meta
WHATSAPP_API_VERSION=v22.0          # opcional, default v22.0
WHATSAPP_APP_SECRET=tu-app-secret   # opcional — si se define, valida firma HMAC de Meta
TEMPLATE_LANGUAGE=es_MX             # opcional, default es_MX

# Debug
DEBUG_WHATSAPP=false                 # si true, adjunta [TOOLS] a cada respuesta
```

---

## Estructura de archivos

```
ms-ai-telephony-agent/
├── main.py                          ← FastAPI: /chat, /campaign, /campaign/dispatch, /webhook, /session
├── requirements.txt
├── scripts/
│   ├── test_agent.py               ← CLI de pruebas (/select, /list, /reset, /perfil)
│   ├── test_prices.py              ← Verificación automática de precios del catálogo
│   ├── test_all_profiles.py        ← Corre mensajes de prueba contra los 18 perfiles del CSV
│   ├── test_cross_plans.py         ← Prueba comparaciones cruzadas de planes entre perfiles
│   ├── test_check_invented_plans.py ← Prueba _check_invented_plans() de reni_agent.py
│   ├── test_router.py              ← Prueba directa del router semántico (classify())
│   ├── test_embeddings.py          ← Exploración directa de la API de embeddings OCI/Cohere
│   └── list_models.py              ← Lista modelos disponibles en OCI Generative AI
├── docs/
│   ├── Masivo_clientes.csv         ← 18 perfiles de clientes para pruebas
│   └── preguntas_frecuentes_planes.md
├── k8s/
│   └── deployment.yaml
├── app/
│   ├── agent/
│   │   └── reni_agent.py           ← Orquestador principal (LLM + CONTRACT + safety nets)
│   ├── router/
│   │   └── semantic_router.py      ← Clasificador de intenciones por embeddings (Cohere/OCI)
│   ├── catalog/
│   │   └── plans.py                ← Catálogo completo — FUENTE DE VERDAD
│   ├── config/
│   │   ├── oci_model.py            ← Modelo OCI via LiteLLM + parche stream_options
│   │   └── logging_config.py       ← Configuración de logging estructurado
│   ├── contract/
│   │   ├── contract_flow.py        ← Flujo OTP determinístico (sin LLM)
│   │   └── post_sale.py            ← Template de confirmación con folio
│   ├── prompts/
│   │   ├── general_rules.py        ← Reglas fijas del agente (743 líneas de reglas de negocio)
│   │   ├── system_prompt.py        ← Contexto dinámico + catálogo inyectado
│   │   └── campaign_template.py    ← Mensaje inicial determinístico (sin LLM)
│   ├── state/
│   │   ├── session.py              ← SessionState (datos del cliente + flags de contrato)
│   │   ├── persistence.py          ← PostgreSQL CRUD (load/save/delete session)
│   │   └── serializer.py           ← SessionState ↔ dict para PostgreSQL
│   ├── tools/
│   │   ├── telcel_tools.py         ← 6 herramientas Strands (make_tools factory)
│   │   └── prospect_loader.py      ← Carga CSV para CLI
│   └── whatsapp/
│       ├── sender.py               ← Envío de mensajes via API de Meta (v22.0)
│       └── command_handler.py      ← Comandos admin /reset, /perfil, /lista vía WhatsApp
├── campaign_app/                    ← App Streamlit SEPARADA de administración (no es el runtime del agente)
│   ├── app.py                       ← Página de bienvenida / índice
│   ├── db/                          ← crud.py, database.py, models.py, seed.py (SQLAlchemy)
│   ├── components/
│   │   └── md_importer.py
│   └── pages/
│       ├── 1_Catalogo.py            ← CRUD de familias, planes, beneficios, FAQs
│       ├── 2_Promociones.py         ← Gestión de promociones (JSON de configuración)
│       ├── 3_Campanas.py            ← Armado de campañas + disparo vía API FastAPI (httpx)
│       ├── 4_Seguimiento.py         ← Dashboard de métricas por campaña
│       └── 5_Crear_desde_imagen.py  ← Placeholder "Próximamente" (sin funcionalidad)
└── tests/
    └── campaign_app/                ← Tests unitarios de campaign_app (crud, md_importer, models)
```

`main.py` importa `campaign_app.db` de forma opcional (try/except) para trazabilidad de campañas —
si falla el import, `_CAMPAIGN_DB_AVAILABLE=False` y el agente conversacional sigue funcionando igual
(`/campaign/dispatch` responde 503).

---

## Flujo completo de un turno

```
Cliente envía mensaje
    │
    ▼
run_turn() en reni_agent.py
    │
    ├── Inicializar plan_anclado si primer turno (recommend_plan())
    │
    ├── ── DETECCIÓN PRE-LLM: TITULAR ────────────────────────────────────────
    │   └── _detect_titular_issues()
    │           ├── No-titular → respuesta fija + is_titular=False
    │           └── Nombre incorrecto → derivar a CAC + nombre_incorrecto=True
    │
    ├── ── STAGE END (cambio ya procesado) ───────────────────────────────────
    │   ├── end_reason=="success" → mensaje de detalle del cambio (plan anterior/nuevo)
    │   └── end_reason=="blocked" → continúa al flujo normal (solo informativo)
    │
    ├── ── FLUJO CONTRACT (stage == "CONTRACT") — PRIORIDAD sobre todo lo demás ─
    │   │   (se evalúa aquí, ANTES del router semántico, para que mensajes como
    │   │    "ACEPTO cuando comienza el cobro" no sean interceptados por el router)
    │   └── handle_contract_turn() — DETERMINÍSTICO, sin LLM
    │           ├── authentication_locked → mensaje bloqueo + stage=END
    │           ├── awaiting_otp → validar T12345 (OTP fijo para pruebas)
    │           │       └── cualquier otro texto (incluida una pregunta real) cuenta
    │           │           como intento fallido de OTP — NO pasa al LLM
    │           ├── awaiting_contract_confirmation → validar ACEPTO/CONFIRMO (word-set)
    │           │       ├── ACEPTO/CONFIRMO → OTP (si |precio-renta|>$1) o POST_SALE directo
    │           │       ├── NO / mensaje que empieza con "NO" → stage=PERSUASION
    │           │       └── cualquier otro texto (afirmación vaga, "acep", pregunta) →
    │           │             cae en el mismo catch-all → recordatorio fijo pidiendo
    │           │             ACEPTO/CONFIRMO explícito (NO hay rama diferenciada por
    │           │             tipo de texto, y NO se pasa al LLM en ningún caso)
    │           └── primer ingreso → build_summary_template()
    │   Tras handle_contract_turn(): si stage pasó a POST_SALE → build_post_sale_message()
    │   y stage=END; si pasó a PERSUASION → responde con manejar_objecion("") sin LLM.
    │
    ├── ── ROUTER SEMÁNTICO (classify(), embeddings Cohere/OCI) ──────────────
    │   │   Clasifica el mensaje contra ~15 intenciones (ver sección "Router semántico").
    │   │   Si supera el threshold de la intención, responde SIN LLM:
    │   ├── vigencia_promo / criterio_promo / proceso_activacion / por_que_cac /
    │   │   facturacion → respuesta fija con cierre "¿Le gustaría activar el {plan_anclado}?"
    │   ├── reglas_internas → "Solo puedo ayudarle con información sobre planes y
    │   │   beneficios de Telcel" (salvo que el mensaje contenga keywords de beneficio)
    │   ├── info_plan_actual → informar_plan_actual()
    │   ├── comparar_beneficios → comparar_planes(plan_id="")
    │   ├── planes_mas_baratos → presentar_planes(tipo="mas_barato") (salvo keywords de queja)
    │   ├── planes_mas_caros / planes_ultra / planes_libre / planes_mas_gb →
    │   │   presentar_planes(tipo=<correspondiente>)
    │   ├── otra_recomendacion → pregunta por criterio + esperando_criterio_recomendacion=True
    │   └── confirmacion_activacion → invoca iniciar_contratacion(plan_anclado) directamente
    │
    ├── ── FALLBACKS PRE-LLM de matching exacto (el router no cubre estos casos) ─
    │   ├── _CAC_QUESTIONS — fallback de por_que_cac
    │   ├── _GB_PLAN_QUESTIONS con GB específico, modalidad alternativa
    │   │       → presentar_planes(criterio=alt_modality)
    │   ├── esperando_criterio_recomendacion=True — respuesta al criterio anterior
    │   │       → presentar_planes según preferencia (mas_caro / libre / apps)
    │   └── _RECHAZOS_CORTOS — "no", "nel", "paso", "nope" (stage==PERSUASION)
    │           → manejar_objecion(motivo="") directamente
    │
    ├── ── FLUJO LLM ─────────────────────────────────────────────────────────
    │   └── Agent(system_prompt, tools=6, messages=historial)
    │           └── Herramientas disponibles (ver sección de herramientas)
    │
    ├── ── SAFETY NET: recuadro/resumen filtrado por el LLM ─────────────────
    │   └── Si response_text contiene "┌─────" o "Resumen de activación"
    │           → se reemplaza con handle_contract_turn() antes de continuar
    │
    ├── ── INTERCEPTAR iniciar_contratacion ─────────────────────────────────
    │   └── Si _tools_invoked contiene "iniciar_contratacion" y stage=="CONTRACT"
    │       (guarda: solo si not session.awaiting_contract_confirmation):
    │           → response_text del LLM se ignora COMPLETAMENTE
    │           → early return con build_summary_template()
    │           → bypasea clean_response
    │
    ├── ── INTERCEPTAR texto rígido ("RESPONDE EXACTAMENTE...") ─────────────
    │   └── Si algún toolResult contiene ese prefijo:
    │           → response_text reemplazado con texto rígido de la herramienta
    │           → early return, bypasea clean_response
    │
    ├── ── FALLBACK / RETRY ──────────────────────────────────────────────────
    │   ├── response_text vacío → mensaje genérico
    │   └── _TOOL_PATTERN detecta tool escrito como texto → reintentar con agente fresco
    │
    ├── ── _check_invented_plans() ───────────────────────────────────────────
    │   └── Detecta si el LLM inventó nombres/precios de planes fuera del catálogo
    │
    ├── ── SAFETY NETS POST-LLM (clean_response) ────────────────────────────
    │   ├── Elimina nombres de tools escritos como texto literal
    │   ├── Elimina corchetes vacíos (artefacto de Llama)
    │   ├── _fix_tuteo() — tienes→tiene, podrías→podría, etc.
    │   ├── _strip_technical_cac_reasons() — ~37 patrones regex de frases de elegibilidad
    │   ├── _fix_incorrect_promo() — quita mención de promo si precio == renta actual
    │   ├── _filter_ineligible_plans() — elimina líneas de planes con precio < renta
    │   ├── _filter_wrong_modality() — elimina sugerencias de activar en modalidad incorrecta
    │   └── Múltiples preguntas → conserva solo la última (cierre de activación)
    │
    ├── _INTERNAL_LEAK_TERMS — si el LLM menciona "OTP"/"Verificación de seguridad"
    │       reemplaza la respuesta completa con texto genérico de proceso
    ├── _strip_incorrect_cac() — elimina derivaciones al CAC para planes activables
    │
    └── Guardar historial en PostgreSQL (máx 20 mensajes = 10 intercambios)
```

**Nota sobre el router semántico**: no es matching de keywords — usa embeddings de
`cohere.embed-multilingual-v3.0` vía OCI y similitud coseno contra frases de referencia
por intención, con un threshold individual por intención (`THRESHOLDS` en
`semantic_router.py`). Si los embeddings de referencia no están cargados (o falla la
llamada a OCI), `classify()` retorna `None` y el turno continúa a los fallbacks/LLM sin
error. Los embeddings de referencia se generan una sola vez al iniciar la app
(`load_reference_embeddings()` en el `startup` de `main.py`).

---

## Flujo de contratación (contract_flow.py)

```
LLM invoca iniciar_contratacion(plan_id)
    ↓
reni_agent intercepta → early return → handle_contract_turn() → build_summary_template()
    ↓
Cliente responde ACEPTO o CONFIRMO  ← detección por word-set, no substring
    ↓
Si precio == renta actual → POST_SALE directo (sin OTP)
Si precio > renta actual → enviar OTP → "ingrese código de SMS"
    ↓
Cliente ingresa T12345 (OTP fijo para pruebas)
    ↓
OTP válido → genera folio TC-XXXXXXXX → stage = POST_SALE
    ↓
build_post_sale_message() → mensaje de confirmación con folio (trato de usted)
    ↓
stage = END
```

**Constantes en contract_flow.py:**
- `OTP_FIXED = "T12345"`, `MAX_OTP_ATTEMPTS = 3`, `MAX_OTP_RESENDS = 3`
- `MAX_OTP_RESENDS` está **declarada pero sin lógica activa** — no hay flujo de reenvío
  de OTP implementado y `otp_resend_count` nunca se incrementa en `contract_flow.py`

**Casos especiales (comportamiento real, verificado en `handle_contract_turn`):**
- OTP incorrecto → máx 3 intentos → bloqueo (`authentication_locked = True`)
- Cliente cancela con "NO" (o cualquier mensaje que **empiece** con "NO", no es un
  word-set puro para este caso) → `stage = PERSUASION` → responde con `manejar_objecion("")`
- Cualquier otro texto durante `awaiting_contract_confirmation` — afirmación vaga
  ("sí", "ok"), confirmación parcial ("acep", "conf"), una pregunta real, o cualquier
  mensaje no reconocido — **cae en el mismo catch-all genérico**: recordatorio fijo
  pidiendo ACEPTO/CONFIRMO explícito. No hay ramas diferenciadas por tipo de texto,
  y en ningún caso se pasa la pregunta al LLM (el docstring de la función menciona esa
  posibilidad, pero esa rama no es alcanzable con la lógica actual)
- Durante `awaiting_otp`, cualquier texto que no sea exactamente `T12345` (incluida
  una pregunta real del cliente) se cuenta como **intento fallido de OTP**, no se
  reenvía al LLM
- No-titular → bloqueo pre-LLM (sin pasar a flujo CONTRACT)
- Nombre incorrecto → bloqueo pre-LLM (derivar a CAC)

---

## Las seis herramientas Strands (`telcel_tools.py`)

Todas se crean como closures en `make_tools(state)` para acceder al estado de sesión.

| Herramienta | Cuándo la invoca el LLM |
|---|---|
| `iniciar_contratacion(plan_id)` | Cliente confirmó querer activar un plan |
| `responder_por_que(tema)` | Cliente pregunta por qué se recomienda algo o hay promoción |
| `presentar_planes(criterio, tipo)` | Cliente pregunta por planes, apps o precios |
| `informar_plan_actual()` | Cliente pregunta qué plan tiene o cuánto paga |
| `manejar_objecion(motivo)` | Cliente rechaza o expresa desinterés |
| `comparar_planes(plan_id)` | Cliente pide comparar su plan con otro |

### `iniciar_contratacion(plan_id)`
- Valida existencia del plan en catálogo
- Valida `precio >= renta_actual - $1.0` (de lo contrario retorna error al LLM). El `1.0`
  está **hardcodeado como literal** en `telcel_tools.py` (10+ veces en el archivo), no
  importado desde `PRICE_TOLERANCE_MXN` (`plans.py:11`) — riesgo de desincronización
  si la tolerancia del catálogo cambia
- Actualiza: `session.plan_selected`, `session.stage = "CONTRACT"`, resetea flags de contrato
- Retorna el marcador `"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\nCONTRATACION_INICIADA"`
  — reni_agent.py detecta el string `"CONTRATACION_INICIADA"` y lo **reemplaza** con
  `build_summary_template()` haciendo early return (no hay ninguna caja `┌─────┐` real)

### `responder_por_que(tema)`
- `tema`: `"plan"` | `"promocion"` | `"modalidad"` | `"criterio"` | `"canal"`
- Retorna siempre texto prefijado con `"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"`
- Respuestas cerradas que el LLM no puede expandir
- Siempre termina con `¿Le gustaría activar el *{plan_anclado}*?`

### `presentar_planes(criterio, tipo="general")`
- `tipo`: `"mas_barato"` | `"mas_caro"` | `"ultra"` | `"libre"` | `"mas_gb"` | `"especifico"` | `"mismo_precio"` | `"apps"` | `"general"`
- `tipo="apps"`: retorna JSON con 7 apps (Libre) o 1 (Ultra: WhatsApp), indica si la app consultada está incluida
- `tipo="mas_barato"`: retorna texto rígido con hasta 3 planes más baratos + cierre con plan anclado
- `tipo="ultra"` / `"libre"` / `"mas_gb"`: actualiza `session.plan_anclado` al más cercano elegible
- `tipo="especifico"`: busca por nombre, precio o GB; si no es activable → info + derivar a Soporte
- `tipo="mismo_precio"`: planes con `|precio - renta| <= $1`
- Si `tipo` no está en la whitelist válida, o si `criterio` es puramente numérico con un
  `tipo` distinto de vacío/`"general"`, la función redirige automáticamente a `"especifico"`
- Detecta si el cliente pide modalidad diferente a la suya → texto rígido de derivación al CAC
- Para tipos con un solo plan elegible → retorna JSON para que el LLM lo redacte (no texto rígido)

### `informar_plan_actual()`
- Compara plan actual con plan anclado (o recommend_plan() si no hay anclado)
- Retorna texto rígido con plan actual + recomendado + diferencia de GB y cashback
- NO usar para preguntas de facturación ni para planes nuevos por nombre

### `manejar_objecion(motivo)`
- Incrementa `session.rejection_count` en cada llamada
- `rejection_count == 0`: primer rechazo → pregunta empática por la duda / deriva a Soporte si hay queja de servicio
- `rejection_count == 1`: segundo rechazo → "cuando guste, aquí estaremos"
- `rejection_count >= 2`: tercer rechazo → cierre definitivo, menciona CAC
- `motivo` vacío para rechazos sin razón; motivo con texto si hay queja de servicio/cobertura

### `comparar_planes(plan_id)`
- Si `plan_id=""`, usa `session.plan_anclado`
- Muestra: delta de GB, delta de precio, ganancia de cashback, apps incluidas, llamadas/SMS
- Si plan es activable: actualiza `plan_anclado`, cierra con pregunta de activación
- Si plan no es activable: info + deriva a Soporte, mantiene `plan_anclado` previo

**Texto rígido**: cuando una herramienta retorna `"RESPONDE EXACTAMENTE CON ESTE TEXTO..."`, `reni_agent.py` intercepta ese resultado y lo envía directamente al cliente sin pasar por el LLM ni por `clean_response`.

---

## El catálogo en el system prompt

El catálogo completo va inyectado en `system_prompt.py` via `build_catalog_block()`.
El modelo NO necesita herramientas para consultar precios, GB ni beneficios.

El bloque incluye:
- **Tabla de activables** con columna `Canal`:
  - `✅ ESTE CANAL` — planes con `precio >= current_cost - 1.0` (activables aquí)
- **Plan informativo más económico** — solo 1 plan (el más barato entre los no elegibles), con nota de que el resto no se menciona
- **Precios en modalidad alternativa** — tabla separada sin columna Canal (todos requieren CAC)
- Sin fechas de vigencia de promoción — solo "24 meses desde la activación"

**NUNCA agregar datos de planes hardcodeados en el prompt** — siempre usar `plans.py`.

---

## Catálogo actual (plans.py)

| Plan | Precio Abierto | Precio Controlado | GB Base | GB Promo | Cashback Ctrl |
|---|---|---|---|---|---|
| Telcel Libre 1 | $249 | $299 | 4 GB | 6 GB | $14.95 |
| Telcel Libre 2 | $319 | $369 | 5 GB | 7.5 GB | $18.45 |
| Telcel Libre 3 | $399 | $449 | 6 GB | 9 GB | $44.90 |
| Telcel Libre 4 | $499 | $549 | 10 GB | 15 GB | $82.35 |
| Telcel Libre 5 | $599 | $699 | 20 GB | 30 GB | $104.85 |
| Telcel Libre 6 | $699 | $799 | 30 GB | 45 GB | $119.85 |
| Telcel Libre 7 | $799 | $899 | 40 GB | 60 GB | $134.85 |
| Telcel Libre 9 | $999 | $1,099 | 45 GB | 67.5 GB | $164.85 |
| Telcel Libre 12 | $1,299 | $1,399 | 55 GB | 82.5 GB | $209.85 |
| Telcel Libre VIP | $1,499 | $1,599 | 40 GB | 60 GB | $671.58 |
| Telcel Ultra 3 | $349 | $399 | 15 GB | — | — |
| Telcel Ultra 4 | $449 | $499 | 25 GB | — | — |
| Telcel Ultra 5 | $549 | $599 | 40 GB | — | — |
| Telcel Ultra 7 | $749 | $799 | 60 GB | — | — |
| Telcel Ultra 9 | $949 | $999 | 100 GB | — | — |
| Telcel Ultra Ilimitado | $1,349 | $1,399 | Ilimitado (PUJ) | — | — |

**Constantes del catálogo:**
- `PRICE_TOLERANCE_MXN = 1.0`
- `PROMO_VIGENCIA = "30/05/2026"` (usado internamente, no se muestra al cliente)
- `PROMO_TERM_MONTHS = 24`
- `LEGACY_PLANS_GB` — mapea nombres de planes anteriores (ej. "Max Sin Límite", "Plus", "TP") a GB para clientes históricos

Promoción de GB: solo aplica en Telcel Libre cuando `precio_nuevo > renta_actual + $1`.

---

## Router semántico (`app/router/semantic_router.py`)

Clasifica el mensaje del cliente en una de ~15 intenciones usando embeddings de
`cohere.embed-multilingual-v3.0` (OCI Generative AI), no matching de keywords.

- `INTENCIONES` — dict de `intencion → [frases de referencia en español, minúsculas, sin acentos/puntuación]`
- `THRESHOLDS` — similitud coseno mínima por intención (0.72–0.82) para aceptar la clasificación
- `load_reference_embeddings()` — genera y cachea en memoria los embeddings de todas las
  frases de referencia; se llama una sola vez en el `startup` de `main.py`
- `classify(message)` — embebe el mensaje del cliente, calcula similitud coseno contra
  todas las frases de referencia, retorna la intención de mayor score si supera su
  threshold, o `None` si no (o si los embeddings no están cargados, o falla la llamada a OCI)

Intenciones actuales: `vigencia_promo`, `criterio_promo`, `reglas_internas`,
`proceso_activacion`, `por_que_cac`, `facturacion`, `info_plan_actual`,
`comparar_beneficios`, `planes_mas_baratos`, `planes_mas_caros`, `planes_ultra`,
`planes_libre`, `planes_mas_gb`, `otra_recomendacion`, `confirmacion_activacion`.

**Para agregar una intención nueva**: agregar sus frases de referencia a `INTENCIONES`,
su threshold a `THRESHOLDS`, y el bloque `elif _intencion == "..."` correspondiente en
`run_turn()` (`reni_agent.py`).

---

## SessionState — todos los campos (session.py)

| Campo | Tipo | Descripción |
|---|---|---|
| `first_name` | `str` | Nombre de pila del cliente |
| `full_name` | `str` | Nombre completo |
| `phone_number` | `str` | Identificador de sesión en PostgreSQL |
| `current_plan_name` | `str` | Nombre del plan actual contratado |
| `current_cost` | `float` | Renta mensual actual |
| `current_plan_gb` | `Optional[float]` | GB del plan actual (si se conoce) |
| `current_plan_cashback` | `Optional[float]` | Cashback del plan actual |
| `previous_plan_name` | `str` | Nombre del plan antes del cambio (default `""`); usado en el mensaje de cierre cuando `stage=="END"` y `end_reason=="success"` |
| `subscription_type` | `str` | `"Abierto"` o `"Controlado"` |
| `has_promotion` | `bool` | Si el cliente tiene promoción activa (default True) |
| `fecha_vigencia` | `str` | Fecha de vigencia de promo (default `"30/05/2026"`) |
| `usage_summary` | `Optional[str]` | Perfil de uso (ej. "uso moderado de datos") |
| `plan_selected` | `Optional[str]` | Plan que el cliente aceptó activar |
| `plan_anclado` | `str` | Plan contextual activo para cierres (se actualiza con cada presentación) |
| `rejection_count` | `int` | Contador de rechazos para manejar_objecion |
| `stage` | `str` | `PERSUASION` → `CONTRACT` → `POST_SALE` → `END` |
| `end_reason` | `str` | `""` \| `"success"` \| `"blocked"` — por qué se llegó a `stage=="END"`; determina el mensaje mostrado en turnos posteriores |
| `esperando_criterio_recomendacion` | `bool` | True si se preguntó "¿qué prefiere?" y se espera respuesta |
| `is_titular` | `bool` | False si se detectó que no es el titular |
| `nombre_incorrecto` | `bool` | True si el cliente reportó discrepancia de nombre |
| `cac_nombre_incorrecto_shown` | `bool` | True si ya se mostró mensaje de derivación por nombre |
| `post_not_titular` | `bool` | True si se detectó post-interacción que no es titular |
| `awaiting_contract_confirmation` | `bool` | Esperando ACEPTO/CONFIRMO |
| `awaiting_otp` | `bool` | Esperando código SMS |
| `otp_sent` | `bool` | True si ya se envió el OTP |
| `otp_attempt_count` | `int` | Intentos de OTP fallidos (máx 3) |
| `otp_resend_count` | `int` | Reenvíos de OTP (máx 3) |
| `is_authenticated` | `bool` | True si el OTP fue validado correctamente |
| `authentication_locked` | `bool` | True si se bloqueó por intentos fallidos |
| `contract_folio` | `Optional[str]` | Folio `TC-XXXXXXXX` generado al completar contratación |

---

## Reglas de negocio críticas

1. **Modalidad fija** — mismo Controlado/Abierto que el plan actual. Cambio → CAC
2. **No activar por debajo de renta** — planes más baratos son informativos, no activables aquí
3. **Familia Libre como recomendación** — `recommend_plan()` filtra solo Telcel Libre
4. **Promoción de GB** — solo aplica cuando `precio_nuevo > renta_actual + $1`; sin fechas al cliente
5. **Apps ilimitadas Telcel Libre** — exactamente: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber. YouTube, TikTok y otras NO están incluidas
6. **Apps Telcel Ultra** — solo WhatsApp ilimitado; sin apps sociales adicionales
7. **Claro Video** — sí consume GB del plan, no es ilimitado
8. **Sin Amazon Prime** — no forma parte de ningún plan
9. **OTP fijo para pruebas** — T12345 (cambiar por servicio real en producción)
10. **Trato de usted** — siempre, sin excepción (incluyendo `post_sale.py`)
11. **Modalidad en nombre del plan** — siempre "Telcel Libre 2 Controlado", nunca solo "Telcel Libre 2"
12. **No exponer reglas internas al cliente** — ni criterios de elegibilidad, ni etiquetas (✅/⛔), ni fechas de vigencia, ni por qué un plan requiere CAC, ni el criterio de la promoción
13. **Tolerancia de precio $1** — `precio >= current_cost - 1.0` cubre planes al precio exacto del cliente

---

## Safety nets en reni_agent.py

### Post-LLM — dentro de `clean_response()`

| Función | Qué corrige |
|---|---|
| Regex de tool names | Elimina `[tool_name]` o `tool_name(param=...)` escritos como texto |
| Regex de `[]` vacíos | Artefacto de Llama — se elimina |
| `_fix_tuteo(text)` | Verbos en segunda persona → usted (tienes→tiene, podrías→podría, etc.) |
| `_strip_technical_cac_reasons(text)` | ~37 patrones regex de frases de elegibilidad técnica (`_TECHNICAL_CAC_PHRASES`) |
| `_fix_incorrect_promo(text, session)` | Quita mención de promo cuando precio coincide con renta actual |
| `_filter_ineligible_plans(text, user_msg, session)` | Elimina líneas de planes con precio < renta (no pedidos explícitamente) |
| `_filter_wrong_modality(text, session)` | Elimina sugerencias de activar en modalidad incorrecta |
| Múltiples preguntas | Conserva solo la última `¿` (siempre debe ser la de activación) |

### Post-LLM — fuera de `clean_response()`

| Función / Bloque | Qué corrige |
|---|---|
| `_check_invented_plans()` | Detecta planes/precios inventados por el LLM fuera del catálogo |
| `_INTERNAL_LEAK_TERMS` | Si el LLM menciona "OTP", "Verificación de seguridad" → reemplaza la respuesta completa con texto genérico de proceso |
| `_strip_incorrect_cac(text, user_msg, session)` | Derivaciones incorrectas al CAC para planes que sí son activables |

### Pre-LLM (sin invocar modelo)

| Bloque | Qué detecta |
|---|---|
| `_detect_titular_issues()` | No-titular y nombre incorrecto → respuesta fija (se evalúa primero, antes del router) |
| `handle_contract_turn()` (`stage=="CONTRACT"`) | Flujo determinístico de contratación — tiene prioridad sobre el router semántico |
| Router semántico `classify()` | Clasifica en ~15 intenciones por embeddings; ver sección "Router semántico" — reemplazó las listas de keywords (`_PROMO_QUESTIONS`, `_REGLAS_QUESTIONS`, `_PROCESO_QUESTIONS`, `_FACTURACION_QUESTIONS`, `_GB_PLAN_QUESTIONS`, `_MAS_BARATO_QUESTIONS`, `_ULTRA_QUESTIONS` — ya no existen en el código) |
| `_CAC_QUESTIONS` | Fallback de matching exacto tras el router (la intención `por_que_cac` ya cubre el caso principal) |
| Modalidad alternativa | "¿En controlado?" → llama `presentar_planes(criterio=alt_modality)` |
| `esperando_criterio_recomendacion` | Respuesta al criterio (GB/cashback/apps) → llama `presentar_planes` según preferencia |
| `_RECHAZOS_CORTOS` | "no", "nel", "paso", "nope" (`stage==PERSUASION`) → llama `manejar_objecion()` |

---

## Problemas conocidos y soluciones aplicadas

### Tool calling con Llama en OCI
Llama 3.3 en OCI a veces escribe el nombre de la herramienta como texto literal.
Safety nets:
1. **Regex pattern** (`_TOOL_PATTERN`) — detecta `[tool_name]` o `tool_name(param)` y reintenta con agente fresco
2. **Interception por `_tools_invoked`** — si invocó `iniciar_contratacion`, `reni_agent.py` ignora el `response_text` del LLM completamente
3. **Texto rígido** — si cualquier herramienta retorna `"RESPONDE EXACTAMENTE..."`, se bypasea el LLM

### Safety net adicional para resumen de contratación
Si el `response_text` contiene `"┌─────"` o `"Resumen de activación"` (el LLM repitió el output interno de `iniciar_contratacion`), se reemplaza con `handle_contract_turn()` antes de continuar.

### `_filter_ineligible_plans` eliminando el plan correcto
**Causa**: el filtro anterior usaba `all()` sobre todos los precios de una línea. El cashback (ej. `$164.85`) al hacer `.replace('.', '')` se convertía en `16485`, que comparado contra la renta fallaba.

**Solución**: usar solo `prices[0]` (primer precio de la línea = precio del plan):
```python
raw = re.sub(r'[,.](?=\d{3}(?:\D|$))', '', prices[0])
plan_price = float(raw.replace(',', ''))
```

### Interception doble de `iniciar_contratacion`
**Causa**: la interception estaba después del fallback. El fallback podía llamar a `handle_contract_turn()` primero, y luego la interception lo llamaba de nuevo.

**Solución**: la interception se hace ANTES del fallback, con early return que bypasea `clean_response` completamente. Además incluye guarda: solo llama a `handle_contract_turn()` si `not session.awaiting_contract_confirmation`.

### Parche OCI stream_options
En `app/config/oci_model.py` hay un parche en memoria que fuerza `drop_params=True`
para que LiteLLM ignore el parámetro `stream_options` que OCI no soporta.
Eliminar cuando LiteLLM corrija esto oficialmente.

### Autenticación OCI en Kubernetes
Si `OCI_USER` no está definido en el entorno, `build_oci_model()` usa `oci_auth="instance_principal"` automáticamente. No se requiere `OCI_SERVICE_ENDPOINT` — la región se pasa via `oci_region`.

---

## Concurrencia en main.py

- **Startup**: `load_reference_embeddings()` del router semántico se ejecuta al iniciar la app (precachea embeddings de referencia)
- **Deduplicación de mensajes**: `_processed_msg_ids` (in-memory set); limpieza automática al llegar a 500 IDs
- **Lock por teléfono**: `_get_phone_lock()` previene turnos simultáneos del mismo número; si ya hay un turno en curso para ese número, el mensaje nuevo se descarta (`acquire(blocking=False)`)
- **Comandos admin**: `handle_command()` intercepta mensajes que empiezan con `/` ANTES del flujo normal del agente
- **Botones interactivos**: si `session.awaiting_contract_confirmation` es True, se envían botones quick_reply de WhatsApp junto con el mensaje
- **Procesamiento en background**: el webhook de WhatsApp retorna 200 inmediatamente; el turno se procesa via `BackgroundTasks`
- **campaign_app.db**: import opcional con try/except; si falla, `_CAMPAIGN_DB_AVAILABLE=False` y el agente conversacional funciona igual (`/campaign/dispatch` responde 503). Actualiza estado de `CampanaCliente` al final de cada turno vía `_maybe_update_campana_cliente()`

---

## Endpoints FastAPI (main.py)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/actuator/health` | — | Health check → `{"status": "UP"}` |
| `POST` | `/chat` | `x-api-key` | Turno de conversación |
| `POST` | `/campaign` | `x-api-key` | Inicia campaña: envía template WhatsApp y crea sesión en PostgreSQL |
| `POST` | `/campaign/dispatch` | `x-api-key` | Batch dispatch desde UI Streamlit (requiere `campaign_app.db`) |
| `DELETE` | `/session` | `x-api-key` | Elimina sesión por `phone_number` |
| `GET` | `/webhook` | — | Verificación de webhook Meta |
| `POST` | `/webhook` | — | Recibe mensajes WhatsApp (BackgroundTasks); valida firma HMAC si `WHATSAPP_APP_SECRET` está definido |

**ChatRequest** — campos opcionales: `message`, `phone_number`, `first_name`, `full_name`, `current_plan_name`, `current_cost`, `current_plan_gb`, `current_plan_cashback`, `subscription_type`, `has_promotion`, `usage_summary`, `is_titular`

El endpoint `/chat` en el primer turno devuelve el mensaje de campaña sin llamar al LLM.

**POST /webhook** soporta tipos de mensaje `text` y `button` (pulsaciones de botones de template quick_reply). Otros tipos se ignoran silenciosamente.

---

## Comandos CLI (test_agent.py / command_handler.py)

```
/list          → lista los 18 perfiles del CSV
/select N      → carga perfil N, genera mensaje de campaña y espera respuesta
/reset         → limpia sesión local y elimina de PostgreSQL
/perfil        → muestra datos del cliente activo
/exit          → salir
```

`command_handler.py` expone los mismos comandos vía WhatsApp para uso admin (sin LLM).

---

## Pendiente de implementar

- [ ] **OTP real** — reemplazar `T12345` en `contract_flow.py` por servicio SMS real
- [ ] **Reenvío de OTP** — `MAX_OTP_RESENDS` está declarada pero sin lógica activa
- [ ] **Logs y métricas** — auditoría de conversaciones y tasa de conversión
- [ ] **Seguridad** — ARCO, tokenización PII
- [ ] **`5_Crear_desde_imagen.py`** en `campaign_app` — placeholder "Próximamente", sin funcionalidad

---

## Cómo agregar nueva funcionalidad

| Qué agregar | Dónde |
|---|---|
| Nueva regla de negocio | `app/prompts/general_rules.py` |
| Nuevo dato contextual del cliente | `app/prompts/system_prompt.py` |
| Nuevo dato del plan | `app/catalog/plans.py` |
| Nueva acción que modifica estado | Nueva herramienta en `app/tools/telcel_tools.py` (agregar a la lista en `make_tools`) |
| Nuevo paso en el flujo de contrato | `app/contract/contract_flow.py` |
| Nuevo safety net de respuesta | Nueva función en `app/agent/reni_agent.py`, llamada desde `clean_response()` |
| Nueva intención pre-LLM | Frases de referencia + threshold en `app/router/semantic_router.py` (`INTENCIONES`/`THRESHOLDS`) y bloque `elif` en `run_turn()` |
| Nueva detección pre-LLM de matching exacto (caso puntual que el router no cubre) | Nuevo bloque en `run_turn()`, después del router semántico |

**NUNCA** hardcodear precios o GB fuera de `plans.py`.  
**NUNCA** exponer al cliente: etiquetas internas (✅/⛔), criterios de elegibilidad, razones técnicas de derivación al CAC, ni el criterio de la promoción.  
**NUNCA** usar `OCI_SERVICE_ENDPOINT` en el `.env` — se calcula internamente desde `OCI_REGION`.
