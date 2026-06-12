# CLAUDE.md — ReniAgent Strands Nativo

Contexto completo para Claude Code. Lee este archivo antes de tocar cualquier código.

---

## ¿Qué es este proyecto?

Agente de ventas Telcel migrado de **LangGraph** a **Strands Agents** con arquitectura nativa.
Atiende clientes por WhatsApp para ofrecerles migración a planes vigentes (Telcel Libre / Ultra).

**Principios de arquitectura:**
- No hay router, no hay nodos, no hay clasificación explícita de intenciones
- El catálogo de planes está inyectado en el system prompt — el modelo razona directamente
- Solo UNA herramienta Strands activa: `iniciar_contratacion`
- El flujo de contratación (CONTRACT) es 100% determinístico — sin LLM
- Persistencia de sesión en PostgreSQL por número de teléfono
- Detecciones pre-LLM para titular, nombre y preguntas sobre promociones

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
VERIFY_TOKEN=tu-verify-token-whatsapp
WHATSAPP_TOKEN=tu-token-meta
WHATSAPP_PHONE_ID=tu-phone-id-meta
```

---

## Estructura de archivos

```
ms-ai-telephony-agent/
├── main.py                          ← FastAPI: /chat, /webhook (WhatsApp), /session
├── scripts/
│   ├── test_agent.py               ← CLI de pruebas (/select, /list, /reset, /perfil)
│   └── test_prices.py              ← Verificación automática de precios del catálogo
├── docs/
│   └── Masivo_clientes.csv         ← 18 perfiles de clientes para pruebas
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
│   │   ├── general_rules.py        ← Reglas fijas del agente (todas las reglas de negocio)
│   │   ├── system_prompt.py        ← Contexto dinámico + catálogo inyectado
│   │   └── campaign_template.py    ← Mensaje inicial determinístico (sin LLM)
│   ├── state/
│   │   ├── session.py              ← SessionState (datos del cliente + flags de contrato)
│   │   ├── persistence.py          ← PostgreSQL CRUD (load/save/delete session)
│   │   └── serializer.py           ← SessionState ↔ dict para PostgreSQL
│   ├── tools/
│   │   ├── telcel_tools.py         ← UNA sola herramienta: iniciar_contratacion
│   │   └── prospect_loader.py      ← Carga CSV para CLI
│   └── whatsapp/
│       ├── sender.py               ← Envío de mensajes via API de Meta
│       └── command_handler.py      ← Comandos /reset, /status vía WhatsApp
```

---

## Flujo completo de un turno

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
    ├── Detección de pregunta sobre promociones [PRE-LLM]
    │       └── Frases como "por qué hay promoción", "cuando aplica la promo"
    │           → respuesta fija con plan recomendado, sin LLM
    │
    ├── session.stage == "CONTRACT"?
    │       ├── Sí → handle_contract_turn() [DETERMINÍSTICO, sin LLM]
    │       │       ├── authentication_locked → mensaje bloqueo + stage=END
    │       │       ├── awaiting_otp → validar T12345 (OTP fijo para pruebas)
    │       │       ├── awaiting_contract_confirmation → validar ACEPTO/CONFIRMO (word-set)
    │       │       │       ├── ACEPTO/CONFIRMO → enviar OTP (o POST_SALE si mismo precio)
    │       │       │       ├── NO/CANCEL → stage=PERSUASION, return None → LLM
    │       │       │       ├── _VAGUE_CONFIRMATIONS → pedir ACEPTO/CONFIRMO
    │       │       │       ├── msg.startswith("ACEP"/"CONF") → pedir ACEPTO/CONFIRMO
    │       │       │       └── otro mensaje → return None → LLM responde
    │       │       └── primer ingreso → build_summary_template()
    │       └── No → flujo LLM
    │
    ├── LLM con system_prompt + herramienta iniciar_contratacion
    │       └── Si LLM invoca iniciar_contratacion → interceptar → early return
    │               (response_text del LLM se ignora COMPLETAMENTE)
    │
    ├── Safety nets post-LLM (clean_response):
    │       ├── _fix_app_mentions() — corrige apps incorrectas (TikTok, YouTube, etc.)
    │       ├── _fix_tuteo() — tienes→tiene, podrías→podría, etc.
    │       ├── _strip_technical_cac_reasons() — elimina 32 patrones de frases técnicas
    │       ├── _fix_incorrect_promo() — quita mención de promo si precio == renta actual
    │       ├── _filter_ineligible_plans() — elimina líneas de planes con precio < renta
    │       └── _filter_wrong_modality() — elimina sugerencias de modalidad incorrecta
    │
    ├── _strip_incorrect_cac() — elimina derivaciones incorrectas al CAC
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

**Casos especiales:**
- OTP incorrecto → máx 3 intentos → bloqueo (`authentication_locked = True`)
- Confirmación parcial ("acep", "conf") → solicitar ACEPTO/CONFIRMO explícito
- Afirmación vaga ("sí", "ok", "dale") → solicitar ACEPTO/CONFIRMO explícito
- Cliente cancela (NO) → `stage = PERSUASION` → LLM retoma persuasión
- Pregunta durante espera de confirmación → `return None` → LLM responde
- No-titular → bloqueo pre-LLM (sin pasar a flujo CONTRACT)
- Nombre incorrecto → bloqueo pre-LLM (derivar a CAC)

---

## La única herramienta Strands

`iniciar_contratacion(plan_id)` en `telcel_tools.py`:
- Valida que el plan existe en el catálogo
- Valida que el precio >= renta actual (de lo contrario retorna error al LLM)
- Actualiza `session.plan_selected` y `session.stage = "CONTRACT"`
- Loggea la invocación con `plan_id`, precio y `phone_number`

**Interception en reni_agent.py** (sin guarda de stage):
```python
if "iniciar_contratacion" in _tools_invoked:
    contract_msg = handle_contract_turn(session, user_message)
    if contract_msg:
        response_text = contract_msg  # reemplaza completamente
    return response_text, updated_history  # early return, bypasea clean_response
```

**NUNCA agregar más herramientas** a menos que sea una acción real que modifique estado.
Las consultas de catálogo van en el system prompt, no en herramientas.

---

## El catálogo en el system prompt

El catálogo completo va inyectado en `system_prompt.py` via `build_catalog_block()`.
El modelo NO necesita herramientas para consultar precios, GB ni beneficios.

El bloque incluye:
- **Una sola tabla unificada** con columna `Canal` por cada plan:
  - `✅ ESTE CANAL` — planes con precio >= renta actual (activables aquí)
  - Tolerancia: `precio >= current_cost - 1.0` (cubre plan exactamente igual a la renta)
- **Plan informativo más económico** — solo 1 plan (el más barato entre los no elegibles),
  con nota de que el resto no se menciona
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

Promoción de GB: solo aplica en Telcel Libre cuando `precio_nuevo > renta_actual + $1`.

---

## SessionState — campos relevantes

| Campo | Tipo | Descripción |
|---|---|---|
| `phone_number` | `str` | Identificador de sesión en PostgreSQL |
| `subscription_type` | `str` | `"Abierto"` o `"Controlado"` |
| `current_cost` | `float` | Renta mensual actual |
| `stage` | `str` | `PERSUASION` → `CONTRACT` → `POST_SALE` → `END` |
| `plan_selected` | `Optional[str]` | Plan que el cliente aceptó activar |
| `is_titular` | `bool` | False si se detectó que no es el titular |
| `nombre_incorrecto` | `bool` | True si el cliente reportó discrepancia de nombre |
| `cac_nombre_incorrecto_shown` | `bool` | True si ya se mostró mensaje de derivación por nombre |
| `post_not_titular` | `bool` | True si se detectó post-interacción que no es titular |
| `awaiting_contract_confirmation` | `bool` | Esperando ACEPTO/CONFIRMO |
| `awaiting_otp` | `bool` | Esperando código SMS |
| `otp_attempt_count` | `int` | Intentos fallidos (máx 3) |
| `authentication_locked` | `bool` | True si se bloqueó por intentos fallidos |
| `contract_folio` | `Optional[str]` | Folio generado al completar contratación |

---

## Reglas de negocio críticas

1. **Modalidad fija** — mismo Controlado/Abierto que el plan actual. Cambio → CAC
2. **No activar por debajo de renta** — planes más baratos son informativos, no activables aquí
3. **Familia Libre como recomendación** — `recommend_plan()` filtra solo Telcel Libre
4. **Promoción de GB** — solo aplica cuando `precio_nuevo > renta_actual + $1`; sin fechas al cliente
5. **Apps ilimitadas Telcel Libre** — exactamente: Facebook, WhatsApp, Messenger, X, Instagram, Snapchat, Uber. YouTube, TikTok y otras NO están incluidas
6. **Sin Amazon Prime** — no forma parte de ningún plan
7. **OTP fijo para pruebas** — T12345 (cambiar por servicio real en producción)
8. **Trato de usted** — siempre, sin excepción (incluyendo `post_sale.py`)
9. **Modalidad en nombre del plan** — siempre "Telcel Libre 2 Controlado", nunca solo "Telcel Libre 2"
10. **No exponer reglas internas al cliente** — ni criterios de elegibilidad, ni etiquetas (✅/⛔), ni fechas de vigencia, ni por qué un plan requiere CAC, ni el criterio de la promoción
11. **Tolerancia de precio $1** — `precio >= current_cost - 1.0` cubre planes al precio exacto del cliente

---

## Safety nets en reni_agent.py

| Función | Qué corrige |
|---|---|
| `_fix_app_mentions(text)` | Apps incorrectas (TikTok, YouTube…) → lista correcta de 7 apps Libre |
| `_fix_tuteo(text)` | Verbos en segunda persona → usted (tienes→tiene, etc.) |
| `_strip_technical_cac_reasons(text)` | 32 patrones regex de frases técnicas de elegibilidad |
| `_fix_incorrect_promo(text, session)` | Mención de promo cuando precio == renta actual |
| `_filter_ineligible_plans(text, user_msg, session)` | Líneas de planes con precio < renta no pedidos explícitamente |
| `_filter_wrong_modality(text, session)` | Sugerencias de activar en modalidad incorrecta |
| `_strip_incorrect_cac(text, user_msg, session)` | Derivaciones incorrectas al CAC (post-`clean_response`) |

Detecciones pre-LLM:

| | Qué detecta |
|---|---|
| `_detect_titular_issues()` | No-titular y nombre incorrecto → respuesta fija sin LLM |
| Bloque `_PROMO_QUESTIONS` | Preguntas sobre criterio de promociones → respuesta fija sin LLM |

---

## Problemas conocidos y soluciones aplicadas

### Tool calling con Llama en OCI
Llama 3.3 en OCI a veces escribe el nombre de la herramienta como texto literal.
Safety nets:
1. **Regex pattern** — detecta `[tool_name]` o `tool_name(param)` y reintenta con agente fresco
2. **Interception sin guarda de stage** — si invocó `iniciar_contratacion`, `reni_agent.py`
   ignora el `response_text` del LLM completamente

### _filter_ineligible_plans eliminando el plan correcto
**Causa**: el filtro usaba `all()` sobre todos los precios de una línea. El cashback (ej. `$164.85`)
al hacer `.replace('.', '')` se convertía en `16485`, que comparado contra la renta fallaba.

**Solución**: usar solo `prices[0]` (primer precio de la línea = precio del plan):
```python
raw = re.sub(r'[,.](?=\d{3}(?:\D|$))', '', prices[0])
plan_price = float(raw.replace(',', ''))
```

### Interception doble de iniciar_contratacion
**Causa**: la interception estaba después del fallback. El fallback podía llamar a
`handle_contract_turn()` primero, y luego la interception lo llamaba de nuevo.

**Solución**: la interception se hace ANTES del fallback, con early return que bypasea
`clean_response` completamente.

### Parche OCI stream_options
En `app/config/oci_model.py` hay un parche en memoria que fuerza `drop_params=True`
para que LiteLLM ignore el parámetro `stream_options` que OCI no soporta.
Eliminar cuando LiteLLM corrija esto oficialmente.

---

## Pendiente de implementar

- [ ] **Migrar consultas de catálogo a herramientas** — actualmente el catálogo completo va en
  el system prompt, lo que puede llevar al modelo a exponer reglas internas. La alternativa
  es exponer herramientas de consulta (ej. `consultar_planes`) y reducir el prompt.
- [ ] **OTP real** — reemplazar `T12345` en `contract_flow.py` por servicio SMS real
- [ ] **Integración WhatsApp completa** — el webhook existe pero falta validación de firma Meta
  y manejo de tipos de mensaje distintos a texto
- [ ] **Logs y métricas** — auditoría de conversaciones y tasa de conversión
- [ ] **Seguridad** — ARCO, tokenización PII
- [ ] **Tests automatizados** — actualmente solo `test_prices.py` y CLI manual

---

## Endpoints FastAPI (main.py)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/actuator/health` | Health check |
| `POST` | `/chat` | Turno de conversación (auth via `x-api-key`) |
| `DELETE` | `/session` | Elimina sesión por teléfono |
| `GET` | `/webhook` | Verificación de webhook Meta |
| `POST` | `/webhook` | Recibe mensajes WhatsApp (procesa en `BackgroundTasks`) |

El endpoint `/chat` en el primer turno devuelve el mensaje de campaña sin llamar al LLM.

---

## Comandos CLI (test_agent.py)

```
/list          → lista los 18 perfiles del CSV
/select N      → carga perfil N, genera mensaje de campaña y espera respuesta
/reset         → limpia sesión local y elimina de PostgreSQL
/perfil        → muestra datos del cliente activo
/exit          → salir
```

---

## Cómo agregar nueva funcionalidad

| Qué agregar | Dónde |
|---|---|
| Nueva regla de negocio | `app/prompts/general_rules.py` |
| Nuevo dato contextual del cliente | `app/prompts/system_prompt.py` |
| Nuevo dato del plan | `app/catalog/plans.py` |
| Nueva acción que modifica estado | Nueva herramienta en `app/tools/telcel_tools.py` |
| Nuevo paso en el flujo de contrato | `app/contract/contract_flow.py` |
| Nuevo safety net de respuesta | Nueva función en `app/agent/reni_agent.py`, llamada desde `clean_response()` |
| Nueva detección pre-LLM | Nuevo bloque en `run_turn()` antes del flujo CONTRACT |

**NUNCA** agregar herramientas para consultas — van en el system prompt.  
**NUNCA** hardcodear precios o GB fuera de `plans.py`.  
**NUNCA** exponer al cliente: etiquetas internas (✅/⛔), criterios de elegibilidad, razones técnicas de derivación al CAC, ni el criterio de la promoción.
