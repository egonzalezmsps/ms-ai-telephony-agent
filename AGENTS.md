# AGENTS.md — ReniAgent Strands Nativo

Contexto completo para Codex. Lee este archivo antes de tocar cualquier código.

---

## ¿Qué es este proyecto?

Agente de ventas Telcel migrado de **LangGraph** a **Strands Agents** con arquitectura nativa.
Atiende clientes por WhatsApp para ofrecerles migración a planes vigentes (Telcel Libre / Ultra).

**Principios de arquitectura:**
- No hay router, no hay nodos, no hay clasificación explícita de intenciones
- El catálogo de planes está inyectado en el system prompt — el modelo razona directamente
- Seis herramientas Strands activas (ver sección de herramientas)
- El flujo de contratación (CONTRACT) es 100% determinístico — sin LLM
- Persistencia de sesión en PostgreSQL por número de teléfono
- 11+ detecciones pre-LLM que interceptan y responden sin invocar al modelo

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

# Debug
DEBUG_WHATSAPP=false                 # si true, adjunta [TOOLS] a cada respuesta
```

---

## Estructura de archivos

```
ms-ai-telephony-agent/
├── main.py                          ← FastAPI: /chat, /webhook (WhatsApp), /session
├── requirements.txt
├── scripts/
│   ├── test_agent.py               ← CLI de pruebas (/select, /list, /reset, /perfil)
│   └── test_prices.py              ← Verificación automática de precios del catálogo
├── docs/
│   ├── Masivo_clientes.csv         ← 18 perfiles de clientes para pruebas
│   └── preguntas_frecuentes_planes.md
├── k8s/
│   └── deployment.yaml
├── app/
│   ├── agent/
│   │   └── reni_agent.py           ← Orquestador principal (LLM + CONTRACT + safety nets)
│   ├── catalog/
│   │   └── plans.py                ← Catálogo completo — FUENTE DE VERDAD
│   ├── config/
│   │   ├── oci_model.py            ← Modelo OCI via LiteLLM + parche stream_options
│   │   └── logging_config.py       ← Configuración de logging estructurado
│   ├── contract/
│   │   ├── contract_flow.py        ← Flujo OTP determinístico (sin LLM)
│   │   └── post_sale.py            ← Template de confirmación con folio
│   ├── prompts/
│   │   ├── general_rules.py        ← Reglas fijas del agente (642 líneas de reglas de negocio)
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
```

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
    ├── ── DETECCIONES PRE-LLM (sin invocar modelo) ──────────────────────────
    │   ├── _detect_titular_issues()
    │   │       ├── No-titular → respuesta fija + is_titular=False
    │   │       └── Nombre incorrecto → derivar a CAC + nombre_incorrecto=True
    │   ├── _PROMO_QUESTIONS — "por qué hay promoción", "cuando aplica la promo"
    │   │       → respuesta fija con plan recomendado
    │   ├── _REGLAS_QUESTIONS — "reglas", "criterios", "cómo funciona", "qué puedes hacer"
    │   │       → "Solo puedo ayudarle con información sobre planes Telcel."
    │   ├── _PROCESO_QUESTIONS — "cuál es el proceso", "pasos para activar", "cómo se activa"
    │   │       → "Es muy sencillo — solo confirme que desea el cambio..."
    │   ├── _CAC_QUESTIONS — "por qué tengo que ir al CAC", "no puedes cambiarlo tú"
    │   │       → explicación de canales especializados, sin razón técnica
    │   ├── _FACTURACION_QUESTIONS — "cobro", "factura", "cuándo me cobran"
    │   │       → derivar a Soporte 800 o app Mi Telcel
    │   ├── _GB_PLAN_QUESTIONS — "cuántos gigas tengo", "cuántos GB tiene mi plan"
    │   │       → llama informar_plan_actual() directamente
    │   ├── _MAS_BARATO_QUESTIONS — "más barato", "más económico", "menos caro"
    │   │       → llama presentar_planes(tipo="mas_barato") directamente
    │   ├── _ULTRA_QUESTIONS — "solo ultra", "quiero ultra", "planes ultra"
    │   │       → llama presentar_planes(tipo="ultra") directamente
    │   ├── modalidad alternativa — "en controlado?", "en abierto?" (diferente a la del cliente)
    │   │       → llama presentar_planes(tipo="general", criterio=alt_modality)
    │   ├── _OTRA_RECOMENDACION — "otra recomendación", "dame otra opción"
    │   │       → pregunta por criterio (GB / cashback / apps) + esperando_criterio_recomendacion=True
    │   ├── esperando_criterio_recomendacion=True — respuesta al criterio anterior
    │   │       → llama presentar_planes según preferencia (mas_caro / libre / apps)
    │   └── _RECHAZOS_CORTOS — "no", "nel", "paso", "nope" (stage==PERSUASION)
    │           → llama manejar_objecion(motivo="") directamente
    │
    ├── ── FLUJO CONTRACT (stage == "CONTRACT") ─────────────────────────────
    │   └── handle_contract_turn() — DETERMINÍSTICO, sin LLM
    │           ├── authentication_locked → mensaje bloqueo + stage=END
    │           ├── awaiting_otp → validar T12345 (OTP fijo para pruebas)
    │           ├── awaiting_contract_confirmation → validar ACEPTO/CONFIRMO
    │           │       ├── ACEPTO/CONFIRMO → OTP (si precio > renta+$1) o POST_SALE directo
    │           │       ├── NO/CANCEL → stage=PERSUASION, return None → LLM
    │           │       ├── afirmación vaga ("sí", "ok") → pedir ACEPTO/CONFIRMO
    │           │       ├── parcial ("acep", "conf") → pedir ACEPTO/CONFIRMO
    │           │       └── pregunta → return None → LLM responde
    │           └── primer ingreso → build_summary_template()
    │
    ├── ── FLUJO LLM ─────────────────────────────────────────────────────────
    │   └── Agent(system_prompt, tools=6, messages=historial)
    │           └── Herramientas disponibles (ver sección de herramientas)
    │
    ├── ── INTERCEPTAR iniciar_contratacion ─────────────────────────────────
    │   └── Si _tools_invoked contiene "iniciar_contratacion" y stage=="CONTRACT":
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
    ├── ── SAFETY NETS POST-LLM (clean_response) ────────────────────────────
    │   ├── Elimina nombres de tools escritos como texto literal
    │   ├── Elimina corchetes vacíos (artefacto de Llama)
    │   ├── _fix_tuteo() — tienes→tiene, podrías→podría, etc.
    │   ├── _strip_technical_cac_reasons() — 32 patrones regex de frases de elegibilidad
    │   ├── _fix_incorrect_promo() — quita mención de promo si precio == renta actual
    │   ├── _filter_ineligible_plans() — elimina líneas de planes con precio < renta
    │   ├── _filter_wrong_modality() — elimina sugerencias de activar en modalidad incorrecta
    │   └── Múltiples preguntas → conserva solo la última (cierre de activación)
    │
    ├── _strip_incorrect_cac() — elimina derivaciones al CAC para planes activables
    │
    └── Guardar historial en PostgreSQL (máx 20 mensajes = 10 intercambios)
```

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

**Casos especiales:**
- OTP incorrecto → máx 3 intentos → bloqueo (`authentication_locked = True`)
- Confirmación parcial ("acep", "conf") → solicitar ACEPTO/CONFIRMO explícito
- Afirmación vaga ("sí", "ok", "dale") → solicitar ACEPTO/CONFIRMO explícito
- Cliente cancela (NO) → `stage = PERSUASION` → LLM retoma persuasión
- Pregunta durante espera de confirmación → `return None` → LLM responde
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
- Valida `precio >= renta_actual - $1.0` (de lo contrario retorna error al LLM)
- Actualiza: `session.plan_selected`, `session.stage = "CONTRACT"`, resetea flags de contrato
- Retorna texto de resumen con caja `┌─────┐` — pero reni_agent.py **reemplaza** este texto con `build_summary_template()` y hace early return

### `responder_por_que(tema)`
- `tema`: `"plan"` | `"promocion"` | `"modalidad"` | `"criterio"` | `"canal"`
- Retorna siempre texto prefijado con `"RESPONDE EXACTAMENTE CON ESTE TEXTO SIN MODIFICAR NADA:\n\n"`
- Respuestas cerradas que el LLM no puede expandir
- Siempre termina con `¿Le gustaría activar el *{plan_anclado}*?`

### `presentar_planes(criterio, tipo)`
- `tipo`: `"mas_barato"` | `"mas_caro"` | `"ultra"` | `"libre"` | `"especifico"` | `"mismo_precio"` | `"apps"` | `"general"`
- `tipo="apps"`: retorna JSON con 7 apps (Libre) o 1 (Ultra: WhatsApp), indica si la app consultada está incluida
- `tipo="mas_barato"`: retorna texto rígido con hasta 3 planes más baratos + cierre con plan anclado
- `tipo="ultra"` / `"libre"`: actualiza `session.plan_anclado` al más cercano elegible
- `tipo="especifico"`: busca por nombre, precio o GB; si no es activable → info + derivar a Soporte
- `tipo="mismo_precio"`: planes con `|precio - renta| <= $1`
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
| `subscription_type` | `str` | `"Abierto"` o `"Controlado"` |
| `has_promotion` | `bool` | Si el cliente tiene promoción activa (default True) |
| `fecha_vigencia` | `str` | Fecha de vigencia de promo (default `"30/05/2026"`) |
| `usage_summary` | `Optional[str]` | Perfil de uso (ej. "uso moderado de datos") |
| `plan_selected` | `Optional[str]` | Plan que el cliente aceptó activar |
| `plan_anclado` | `str` | Plan contextual activo para cierres (se actualiza con cada presentación) |
| `rejection_count` | `int` | Contador de rechazos para manejar_objecion |
| `stage` | `str` | `PERSUASION` → `CONTRACT` → `POST_SALE` → `END` |
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
| `_strip_technical_cac_reasons(text)` | 32 patrones regex de frases de elegibilidad técnica |
| `_fix_incorrect_promo(text, session)` | Quita mención de promo cuando precio coincide con renta actual |
| `_filter_ineligible_plans(text, user_msg, session)` | Elimina líneas de planes con precio < renta (no pedidos explícitamente) |
| `_filter_wrong_modality(text, session)` | Elimina sugerencias de activar en modalidad incorrecta |
| Múltiples preguntas | Conserva solo la última `¿` (siempre debe ser la de activación) |

### Post-LLM — fuera de `clean_response()`

| Función / Bloque | Qué corrige |
|---|---|
| `_INTERNAL_LEAK_TERMS` | Si el LLM menciona "OTP", "Verificación de seguridad" → reemplaza la respuesta completa con texto genérico de proceso |
| `_strip_incorrect_cac(text, user_msg, session)` | Derivaciones incorrectas al CAC para planes que sí son activables |

### Pre-LLM (sin invocar modelo)

| Bloque | Qué detecta |
|---|---|
| `_detect_titular_issues()` | No-titular y nombre incorrecto → respuesta fija |
| `_PROMO_QUESTIONS` | Preguntas sobre criterio de promociones → respuesta fija |
| `_REGLAS_QUESTIONS` | Preguntas sobre reglas/criterios internos → respuesta fija |
| `_PROCESO_QUESTIONS` | Preguntas sobre el proceso de activación → respuesta fija |
| `_CAC_QUESTIONS` | "¿Por qué tengo que ir al CAC?" → explicación sin razón técnica |
| `_FACTURACION_QUESTIONS` | Preguntas de facturación → deriva a Soporte/Mi Telcel |
| `_GB_PLAN_QUESTIONS` | "¿Cuántos GB tengo?" → llama `informar_plan_actual()` |
| `_MAS_BARATO_QUESTIONS` | "¿Algo más barato?" → llama `presentar_planes(tipo="mas_barato")` |
| `_ULTRA_QUESTIONS` | "Solo ultra" / "quiero ultra" → llama `presentar_planes(tipo="ultra")` |
| Modalidad alternativa | "¿En controlado?" → llama `presentar_planes(criterio=alt_modality)` |
| `_OTRA_RECOMENDACION` | "Otra recomendación" → pregunta por criterio + flag `esperando_criterio_recomendacion` |
| `esperando_criterio_recomendacion` | Respuesta al criterio → llama `presentar_planes` según preferencia |
| `_RECHAZOS_CORTOS` | "no", "nel", "paso", "nope" → llama `manejar_objecion()` |

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

- **Deduplicación de mensajes**: `_processed_msg_ids` (in-memory set); limpieza automática al llegar a 500 IDs
- **Lock por teléfono**: `_get_phone_lock()` previene turnos simultáneos del mismo número
- **Procesamiento en background**: el webhook de WhatsApp retorna 200 inmediatamente; el turno se procesa via `BackgroundTasks`

---

## Endpoints FastAPI (main.py)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/actuator/health` | — | Health check → `{"status": "UP"}` |
| `POST` | `/chat` | `x-api-key` | Turno de conversación |
| `DELETE` | `/session` | `x-api-key` | Elimina sesión por `phone_number` |
| `GET` | `/webhook` | — | Verificación de webhook Meta |
| `POST` | `/webhook` | — | Recibe mensajes WhatsApp (BackgroundTasks) |

**ChatRequest** — campos opcionales: `message`, `phone_number`, `first_name`, `full_name`, `current_plan_name`, `current_cost`, `current_plan_gb`, `current_plan_cashback`, `subscription_type`, `has_promotion`, `usage_summary`, `is_titular`

El endpoint `/chat` en el primer turno devuelve el mensaje de campaña sin llamar al LLM.

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
- [ ] **Integración WhatsApp completa** — falta validación de firma Meta y manejo de tipos de mensaje distintos a texto
- [ ] **Logs y métricas** — auditoría de conversaciones y tasa de conversión
- [ ] **Seguridad** — ARCO, tokenización PII
- [ ] **Tests automatizados** — actualmente solo `test_prices.py` y CLI manual

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
| Nueva detección pre-LLM | Nuevo bloque en `run_turn()` antes del bloque `if session.stage == "CONTRACT"` |

**NUNCA** hardcodear precios o GB fuera de `plans.py`.  
**NUNCA** exponer al cliente: etiquetas internas (✅/⛔), criterios de elegibilidad, razones técnicas de derivación al CAC, ni el criterio de la promoción.  
**NUNCA** usar `OCI_SERVICE_ENDPOINT` en el `.env` — se calcula internamente desde `OCI_REGION`.
