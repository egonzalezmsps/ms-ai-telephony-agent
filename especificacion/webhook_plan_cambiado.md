# Webhook: Plan Cambiado



> **Estado actual: solo especificación.** Este endpoint todavía no está implementado en
> `main.py` — este documento y el YAML son el contrato propuesto para cuando se decida
> construirlo.

---

## ¿Qué problema resuelve?

Hoy, la única forma en que ReniAgent se entera de que el plan de un cliente ya cambió es
**internamente**, cuando el propio flujo de contratación (`app/contract/contract_flow.py` →
`app/contract/post_sale.py`) completa el proceso de OTP + confirmación dentro de una
conversación de WhatsApp. En ese momento:

- `build_post_sale_message()` actualiza `session.previous_plan_name`, `session.current_plan_name`
  y `session.current_cost`.
- Se marca `session.end_reason = "success"` y `session.stage = "END"`.
- Turnos posteriores del cliente responden con un mensaje fijo de "su cambio de plan ya fue
  procesado".

El problema: **si el cambio de plan se origina fuera de esta conversación** (por ejemplo, un
ejecutivo de CAC lo hace manualmente, o un sistema core de Telcel procesa la migración por otro
canal), ReniAgent nunca se entera. La sesión sigue en `PERSUASION` o `CONTRACT` y el agente
puede seguir intentando vender un plan que el cliente ya activó por otra vía.

Este webhook resuelve eso: le da a un **sistema externo** una forma de avisarle a ReniAgent
"este número ya cambió de plan", para que la conversación se pueda cerrar/actualizar sin
depender de que el cliente vuelva a escribir.

---

## ¿Qué hace el endpoint (comportamiento esperado)?

`POST /webhook/plan-cambiado`

1. Valida el header `x-api-key` contra la misma variable de entorno `API_KEY` que usan
   `/chat`, `/campaign`, `/campaign/dispatch` y `/session` hoy en `main.py`. Si no coincide →
   `401 { "detail": "Invalid API key" }`.
2. Valida que el body traiga `phone_number` (string, requerido). Si falta o el body es
   inválido → `400 { "detail": "phone_number is required" }`.
3. Busca la sesión activa asociada a ese número (mismo mecanismo que ya usa `load_session()`
   en `app/state/persistence.py`, y el mismo helper `_to_linea()` de `main.py` para normalizar
   el número si hace falta cruzarlo contra `campaign_app`). Si no existe sesión → `404
   { "detail": "Session not found" }`.
4. Si todo es válido, procesa la notificación: internamente (cuando se implemente) esto
   implicaría cargar la sesión, marcarla como resuelta de forma equivalente a como lo hace
   hoy `build_post_sale_message()` (actualizar `current_plan_name`/`previous_plan_name`,
   `end_reason = "success"`, `stage = "END"`) y guardar con `save_session(...)`.
5. Responde `200` confirmando la recepción — ver ejemplo abajo.

El endpoint es **idempotente por diseño de uso**: está pensado para poder reintentarse sin
duplicar efectos, apoyándose en `X-Request-Id` (ver siguiente sección) para que quien lo
implemente pueda deduplicar reintentos del sistema emisor.

---

## Request

### Headers

| Header | Requerido | Ya existía en el repo | Por qué se agregó / para qué sirve |
|---|---|---|---|
| `x-api-key` | Sí | Sí (idéntico a `/chat`, `/campaign`, `/campaign/dispatch`, `/session`) | Autenticación del sistema llamante. Se reutiliza el mismo esquema que ya usa todo el repo (`main.py`) en vez de inventar uno nuevo — mismo `HTTPException(401, "Invalid API key")`. |
| `X-Request-Id` | No (recomendado) | **No, es nuevo** | No existe ningún header de correlación en el repo hoy. Se agrega porque este webhook lo dispara un sistema externo que puede reintentar en caso de timeout/error de red; un UUID por notificación permite (a) correlacionar logs entre el sistema emisor y ReniAgent, y (b) deduplicar reintentos para no procesar el mismo cambio de plan dos veces. |
| `X-Source-System` | No | **No, es nuevo** | Más de un sistema podría terminar llamando este webhook (CRM, core Telcel, herramienta interna de CAC). Este header identifica el origen para auditoría — sin él, los logs no distinguirían quién notificó cada cambio. |

**Nota de diseño**: se evaluó también usar una firma HMAC tipo `X-Hub-Signature-256`
(el mismo patrón que ya usa `POST /webhook` para validar mensajes de Meta/WhatsApp en
`main.py`, con `WHATSAPP_APP_SECRET`). Se dejó fuera de esta primera versión porque el
usuario pidió específicamente `x-api-key` como mecanismo de seguridad; si el sistema
emisor requiere garantías criptográficas adicionales sobre la integridad del body, ese
patrón HMAC ya probado en el repo es el candidato natural a agregar después.

### Body

```json
{
  "phone_number": "5215512345678"
}
```

- `phone_number` (string, requerido): mismo formato que ya aceptan `/chat` y `/session` —
  puede ser el `wa_id` completo de WhatsApp (ej. `"5215512345678"`, con `521` o `52` de
  prefijo) o la línea de 10 dígitos sin código de país. No se agregó ningún otro campo al
  body porque el requerimiento original es explícito: el webhook solo necesita el número
  para saber que ese cliente ya cambió de plan.

---

## Response

### 200 — Notificación recibida

```json
{
  "phone_number": "5215512345678",
  "status": "received",
  "received_at": "2026-08-14T15:32:07Z"
}
```

- `phone_number`: eco del número recibido.
- `status`: siempre `"received"` en esta versión — confirma que ReniAgent aceptó y procesó
  la notificación.
- `received_at`: timestamp UTC (ISO 8601) de cuándo se procesó, útil para que el sistema
  emisor pueda auditar la latencia de su propia notificación.

### 400 — Body inválido

```json
{ "detail": "phone_number is required" }
```

### 401 — API key inválida o ausente

```json
{ "detail": "Invalid API key" }
```

Mismo texto exacto que usa `main.py` hoy para todos los demás endpoints protegidos.

### 404 — No hay sesión activa para ese número

```json
{ "detail": "Session not found" }
```

Se documenta este caso porque, a diferencia de `/chat` (que puede crear una sesión nueva en
el primer turno), este webhook no tiene sentido si no hay una conversación previa que cerrar
— no se decidió crear sesiones "vacías" solo para marcarlas como terminadas.

---

## Convenciones que se mantuvieron del resto del repo

- **snake_case** en todos los campos del body/response (`phone_number`, `status`,
  `received_at`), igual que `ChatRequest`, `SessionDeleteRequest`, etc. — nunca camelCase.
- **Envelope de error** `{"detail": "..."}` — es el único formato de error que usa FastAPI
  por defecto y el único que existe en todo el repo; no se inventó un esquema de error nuevo.
- **Autenticación por header, no por query param** — replica `/campaign`, `/campaign/dispatch`
  y `/session`, evitando el patrón inconsistente que sí existe en `/logs` (que usa `?api_key=`
  como query param).

## Pendiente si se decide implementar

- Definir en qué archivo vive el handler (`main.py`, siguiendo el patrón de los demás
  endpoints) y cómo se actualiza `SessionState` sin pasar por un turno completo del LLM
  (hoy no existe una función de "actualización parcial" de sesión — `save_session()` siempre
  espera `session_data` + `history` completos).
- Decidir si también debe reflejarse en `campaign_app` (tabla `CampanaCliente`, vía
  `update_interaction()` en `campaign_app/db/crud.py`) cuando el número pertenezca a una
  campaña activa.
