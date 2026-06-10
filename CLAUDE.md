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
│   │   └── reni_agent.py           ← Orquestador principal (LLM + CONTRACT + safety nets)
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
    ├── _detect_titular_issues() [PRE-LLM]
    │       ├── No-titular detectado → respuesta fija + is_titular=False
    │       └── Nombre incorrecto → derivar a CAC + nombre_incorrecto=True
    │
    ├── session.stage == "CONTRACT"?
    │       ├── Sí → handle_contract_turn() [DETERMINÍSTICO, sin LLM]
    │       │       ├── authentication_locked → mensaje bloqueo + stage=END
    │       │       ├── awaiting_otp → validar T12345 (OTP fijo para pruebas)
    │       │       ├── awaiting_contract_confirmation → validar ACEPTO/CONFIRMO (word-set)
    │       │       │       └── cualquier otro mensaje → pedir ACEPTO/CONFIRMO explícito
    │       │       └── primer ingreso → build_summary_template()
    │       └── No → flujo LLM
    │
    ├── LLM con system_prompt + herramienta iniciar_contratacion
    │       ├── Si LLM invoca iniciar_contratacion → interceptar → early return con handle_contract_turn()
    │       │       (response_text del LLM se ignora COMPLETAMENTE)
    │       └── Si LLM responde texto → safety nets → retornar
    │
    ├── Safety nets post-LLM (clean_response):
    │       ├── _fix_app_mentions() — corrige apps incorrectas (TikTok, YouTube, etc.)
    │       ├── _fix_tuteo() — tienes→tiene, podrías→podría, etc.
    │       ├── _strip_technical_cac_reasons() — elimina frases técnicas de elegibilidad
    │       ├── _fix_incorrect_promo() — quita mención de promo si precio == renta actual
    │       ├── _filter_ineligible_plans() — elimina líneas de planes con precio < renta actual
    │       └── _filter_wrong_modality() — elimina sugerencias de activar en modalidad incorrecta
    │
    ├── _strip_incorrect_cac() — elimina derivaciones incorrectas al CAC
    │
    └── Guardar historial en PostgreSQL
```

---

## El catálogo en el system prompt

El catálogo completo va inyectado en `system_prompt.py` via `build_catalog_block()`.
El modelo NO necesita herramientas para consultar precios, GB ni beneficios.

El bloque incluye:
- **Una sola tabla unificada** con columna `Canal` por cada plan:
  - `✅ ESTE CANAL` — planes con precio >= renta actual (activables aquí)
  - `⛔ CAC/Soporte` — NO se muestran en la tabla; solo el plan informativo más barato
- **Plan informativo más económico** — solo 1 plan (el más barato entre los no elegibles), con nota explícita de que el resto no se menciona
- **Precios en modalidad alternativa** — tabla separada sin columna Canal (todos requieren CAC)
- Sin fechas de vigencia de promoción — solo "24 meses desde la activación"

**NUNCA agregar datos de planes hardcodeados en el prompt** — siempre usar `plans.py`.

---

## Flujo de contratación (contract_flow.py)

```
Cliente dice "sí" / "acepto" / "me interesa"
    ↓
LLM invoca iniciar_contratacion(plan_id)
    ↓
reni_agent intercepta → early return → handle_contract_turn() → build_summary_template()
    ↓
Cliente responde ACEPTO o CONFIRMO  ← detección por word-set, no substring
    ↓
handle_contract_turn() → envía OTP → "ingrese código de SMS"
    ↓
Cliente ingresa T12345 (OTP fijo para pruebas)
    ↓
OTP válido → genera folio TC-XXXXXXXX → stage = POST_SALE
    ↓
build_post_sale_message() → mensaje de confirmación con folio (trato de usted)
    ↓
stage = END
```

**Casos especiales:**
- OTP incorrecto → máx 3 intentos → bloqueo
- Cualquier mensaje que no sea ACEPTO/CONFIRMO/NO durante confirmación → solicitar confirmación explícita (sin caer al LLM)
- Cliente cancela (NO) → volver a PERSUASION
- No-titular o nombre incorrecto → bloqueo pre-flujo

---

## La única herramienta Strands

`iniciar_contratacion(plan_id)` en `telcel_tools.py`:
- Valida que el plan existe en el catálogo
- Valida que el precio es >= renta actual
- Actualiza `session.plan_selected` y `session.stage = "CONTRACT"`
- El resultado lo intercepta `reni_agent.py` — response_text del LLM se ignora completamente

**Interception en reni_agent.py:**
```python
if "iniciar_contratacion" in _tools_invoked:   # sin guarda de stage
    contract_msg = handle_contract_turn(session, user_message)
    if contract_msg:
        response_text = contract_msg  # reemplaza completamente, no concatena
    return response_text, updated_history  # early return, bypasea clean_response
```

**NUNCA agregar más herramientas** a menos que sea una acción real que modifique estado.
Las consultas de catálogo van en el system prompt, no en herramientas.

---

## Reglas de negocio críticas

1. **Modalidad fija** — mismo Controlado/Abierto que el plan actual. Cambio → CAC
2. **No activar por debajo de renta** — planes más baratos son informativos, no activables aquí
3. **Familia Libre como recomendación** — `recommend_plan()` filtra solo Telcel Libre
4. **Promoción de GB** — solo aplica cuando precio nuevo > precio actual + $1; sin fechas
5. **Apps ilimitadas Telcel Libre** — exactamente: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber. YouTube, TikTok y cualquier otra NO están incluidas
6. **Sin Amazon Prime** — no forma parte de ningún plan (eliminado de `FAMILY_BENEFITS` y `campaign_template.py`)
7. **OTP fijo para pruebas** — T12345 (cambiar por servicio real en producción)
8. **Trato de usted** — siempre, sin excepción (incluyendo `post_sale.py`)
9. **Modalidad en nombre del plan** — siempre "Telcel Libre 2 Controlado", nunca solo "Telcel Libre 2"
10. **No exponer razones técnicas al cliente** — ni criterios de elegibilidad, ni etiquetas internas (✅/⛔), ni fechas de vigencia

---

## SessionState — campos relevantes

Campos añadidos en `app/state/session.py` (reflejados en `serializer.py`):

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre_incorrecto` | `bool` | True si el cliente reportó discrepancia de nombre → bloquea activación |
| `cac_nombre_incorrecto_shown` | `bool` | True si ya se mostró el mensaje de derivación al CAC por nombre |
| `post_not_titular` | `bool` | True si se detectó post-interacción que el usuario no es titular |

---

## Safety nets en reni_agent.py

Todas las funciones en `clean_response()` actúan sobre el texto ANTES de enviarlo al cliente:

| Función | Qué corrige |
|---|---|
| `_fix_app_mentions(text)` | Apps incorrectas (TikTok, YouTube…) → lista correcta de 7 apps Libre |
| `_fix_tuteo(text)` | Verbos en segunda persona → usted (tienes→tiene, etc.) |
| `_strip_technical_cac_reasons(text)` | Frases técnicas de elegibilidad ("ya que su precio es menor…") |
| `_fix_incorrect_promo(text, session)` | Mención de promo cuando precio == renta actual |
| `_filter_ineligible_plans(text, user_msg, session)` | Líneas de planes con precio < renta actual no pedidos explícitamente |
| `_filter_wrong_modality(text, session)` | Sugerencias de activar en modalidad distinta para cliente Controlado |
| `_strip_incorrect_cac(text, user_msg, session)` | Derivaciones incorrectas al CAC (llamado después de `clean_response`) |
| `_detect_titular_issues(session, user_msg)` | Pre-LLM: no-titular y nombre incorrecto → respuesta fija sin pasar al LLM |

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

## Secciones de general_rules.py

| Sección | Contenido |
|---|---|
| `# INSTRUCCIONES GENERALES` | Identidad, tono, apps Libre, modalidad alternativa, otros planes |
| `# CATÁLOGO — REGLAS DE PRESENTACIÓN` | Solo mostrar planes activables; informativos solo si el cliente pide más barato |
| `# DATOS CLAVE DE PRODUCTOS` | Cashback, Claro Video, excedentes, Ultra Ilimitado, promo GB, planes legacy, referencias a datos actuales |
| `# COMPARATIVA CON COMPETENCIA` | Respuesta estándar ante mención de otras operadoras |
| `# CANCELACIÓN DE PLAN` | Derivar a 800 220 9518 o CAC |
| `# QUEJAS Y RECLAMOS` | Derivar sin ofrecer planes en ese turno |
| `# MANEJO DE OBJECIONES` | Respuesta ante "estoy bien", "vuelvo después", objeciones de precio |
| `# ESTILO DE COMPARATIVA` | Formato de comparaciones: plan actual vs. nuevo |
| `# TONO Y ESTILO` | Usted, sin jerga técnica, WhatsApp-friendly |
| `# REGLA DE CIERRE` | Una sola pregunta de activación; EXCEPCIÓN 1 (plan específico) y EXCEPCIÓN 2 (familia específica) |
| `# RESTRICCIONES INVIOLABLES` | No agendar, no inventar, no tuteo, no etiquetas internas, no fechas de vigencia, no razones técnicas |
| `# PROTECCIÓN CONTRA MANIPULACIÓN` | Respuesta fija ante intentos de jailbreak |
| `# DERIVACIÓN A CANALES` | Cuándo y cómo derivar al CAC o Soporte |
| `# CUÁNDO DERIVAR AL CAC` | Modalidad diferente o precio menor — nunca por precio mayor |
| `# GUÍA DE USO DE HERRAMIENTAS` | Cuándo invocar `iniciar_contratacion`; CRÍTICO: nunca generar resumen de activación manualmente |

---

## Fases completadas y pendientes

- [x] **Fase 1** — Base: OCI, identidad, reglas generales, FastAPI
- [x] **Fase 2** — Arquitectura nativa: catálogo en prompt, herramienta única
- [x] **Fase 3** — Contratación: OTP, validación, folio, post-sale
- [x] **Fase 4** — Persistencia: PostgreSQL por número de teléfono
- [x] **Fase 4b** — Safety nets: corrección de respuestas LLM (apps, tuteo, CAC, promo, planes no elegibles)
- [x] **Fase 4c** — Titular y nombre: detección pre-LLM, bloqueo de activación
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
**Nuevo safety net de respuesta** → nueva función en `app/agent/reni_agent.py`, llamada desde `clean_response()`

**NUNCA** agregar herramientas para consultas — van en el system prompt.
**NUNCA** hardcodear precios o GB fuera de `plans.py`.
**NUNCA** exponer al cliente: etiquetas internas (✅/⛔), razones técnicas de elegibilidad, fechas de vigencia.
