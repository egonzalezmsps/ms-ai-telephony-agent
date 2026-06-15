# Campaign Creator Interface — Diseño

**Fecha:** 2026-06-15
**Branch:** f_campaing_creator_interface
**Stack:** Streamlit + SQLAlchemy + PostgreSQL (misma DB que Reni)

---

## Contexto

Reni es un agente de ventas Telcel que atiende clientes por WhatsApp ofreciendo migración a planes vigentes. Actualmente los datos de planes están hardcodeados en `plans.py` y los clientes se cargan desde un CSV. Esta interfaz introduce una base de datos como fuente de verdad para campañas, clientes, planes y el catálogo completo, permitiendo gestionar todo sin tocar código.

Una **campaña** es una estrategia de mercado con vigencia y reglas propias, dirigida a un segmento de clientes, con planes y promociones específicas. Ejemplo: migración de familias legacy a familias vigentes con oferta de +GB por upsell.

---

## Decisiones de diseño

- **Streamlit** como framework UI — velocidad de desarrollo, Python puro, sin frontend separado
- **Mock en paralelo** — la DB coexiste con `plans.py` durante esta fase; el agente no se modifica
- **Seed script** — puebla la DB con los datos actuales de `plans.py` y el CSV existente
- **Fuente de verdad final** — en producción, Reni leerá directamente de la DB; las reglas de negocio (safety nets, detecciones) permanecen en código

---

## Esquema de base de datos

### Relaciones

```
Familia ──< FamiliaBeneficio >── Beneficio ──< PreguntaFrecuente
  │    └──< FamiliaServicio  >── Servicio  ──< PreguntaFrecuente
  └──< Plan

Promocion ──< CampanaPlan >── Plan
Campana   ──< CampanaPlan
  └──< CampanaCliente >── Cliente
```

### Tablas

#### `Familia`
| Campo | Tipo | Notas |
|---|---|---|
| id | PK | |
| nombre | str | "Telcel Libre", "Telcel Ultra" |
| descripcion | text | |

#### `Plan`
| Campo | Tipo | Notas |
|---|---|---|
| id | PK | |
| familia_id | FK → Familia | |
| nombre | str | "Telcel Libre 1", "Telcel Ultra 3", etc. |
| precio_abierto | float | |
| precio_controlado | float | |
| gb_base | float | 0 = ilimitado (sujeto a PUJ) |
| tiene_cashback | bool | Solo Telcel Libre |
| cashback_porcentaje | float | 0 si tiene_cashback=False. Cashback calculado = precio × porcentaje |
| activo | bool | |

> **Cashback calculado:** `precio_plan × cashback_porcentaje / 100`. Si el precio cambia, el cashback se recalcula automáticamente sin doble mantenimiento.

#### `Beneficio`
Atributo intrínseco de la familia: Llamadas y SMS ilimitados, Apps ilimitadas.

| Campo | Tipo | Notas |
|---|---|---|
| id | PK | |
| nombre | str | |
| descripcion | text | |
| activo | bool | |

#### `Servicio`
Añadido de la familia: Claro Video, Claro Drive.

| Campo | Tipo | Notas |
|---|---|---|
| id | PK | |
| nombre | str | |
| descripcion | text | |
| tipo_acceso | enum | `suscripcion` \| `acceso` |
| detalle | str | nullable, ej. "20 GB en la nube" |
| activo | bool | |

#### `FamiliaBeneficio`
| Campo | Tipo |
|---|---|
| familia_id | FK → Familia |
| beneficio_id | FK → Beneficio |

#### `FamiliaServicio`
| Campo | Tipo |
|---|---|
| familia_id | FK → Familia |
| servicio_id | FK → Servicio |

#### `PreguntaFrecuente`
El ciclo de vida depende del beneficio o servicio al que está ligada. Si el beneficio/servicio se elimina, sus FAQs se eliminan en cascada.

| Campo | Tipo | Notas |
|---|---|---|
| id | PK | |
| beneficio_id | FK → Beneficio | nullable, CASCADE DELETE |
| servicio_id | FK → Servicio | nullable, CASCADE DELETE |
| ambito | enum | `beneficio` \| `servicio` \| `general` |
| pregunta | text | |
| respuesta | text | |
| activo | bool | |

> Una FAQ tiene `beneficio_id` OR `servicio_id` OR ninguno (general). No ambos.

#### `Promocion`
Diseño flexible — no se limita el tipo de promoción.

| Campo | Tipo | Notas |
|---|---|---|
| id | PK | |
| nombre | str | |
| descripcion | text | |
| vigencia_inicio | date | |
| vigencia_fin | date | |
| configuracion | JSON | Estructura libre según tipo de promo |
| condicion | text | Cuándo aplica, ej. "upsell" |
| activo | bool | |

> Ejemplos de `configuracion`:
> ```json
> { "tipo": "multiplicador_gb", "valor": 1.5 }
> { "tipo": "descuento_porcentaje", "valor": 10 }
> { "tipo": "servicio_gratis", "servicio": "Amazon Prime", "meses": 3 }
> ```

#### `Campana`
| Campo | Tipo | Notas |
|---|---|---|
| id | PK | |
| nombre | str | |
| descripcion | text | |
| creado_en | datetime | Cuándo se creó en el sistema |
| vigencia_inicio | date | Cuándo inicia (puede ser futura) |
| vigencia_fin | date | |
| estado | enum | `borrador` \| `activa` \| `pausada` \| `finalizada` |
| reglas_elegibilidad | JSON | Criterios de filtro de clientes |

#### `CampanaPlan`
PK compuesta: (campana_id, plan_id)

| Campo | Tipo | Notas |
|---|---|---|
| campana_id | FK → Campana | PK |
| plan_id | FK → Plan | PK |
| promocion_id | FK → Promocion | nullable |

#### `Cliente`
| Campo | Tipo | Notas |
|---|---|---|
| linea | PK (str) | Número de teléfono |
| nombre | str | |
| apellidos | str | |
| plan_actual_nombre | str | |
| familia_plan | str | |
| tipo_suscripcion | str | Abierto / Controlado / Mixto / Postpago |
| renta_plan | float | |
| facturacion_promedio | float | |
| consumo_mb_total_prom | float | |
| consumo_mb_whatsapp_prom | float | |
| consumo_mb_redes_prom | float | |
| consumo_mb_youtube_prom | float | |
| consumo_mb_uber_prom | float | |
| consumo_mb_instagram_prom | float | |
| consumo_mb_otros_prom | float | |
| excedentes_nac_mb_prom | float | |
| excedentes_int_mb_prom | float | |
| ingresos_exc_nac_prom | float | |
| ingresos_exc_int_prom | float | |
| creado_en | datetime | |

#### `CampanaCliente`
PK compuesta: (campana_id, linea)

| Campo | Tipo | Notas |
|---|---|---|
| campana_id | FK → Campana | PK |
| linea | FK → Cliente | PK |
| estado_envio | enum | `pendiente` \| `enviado` \| `fallido` |
| fecha_envio | datetime | nullable |
| estado_interaccion | enum | `pendiente` \| `en_conversacion` \| `interesado` \| `convertido` \| `rechazado` |
| plan_seleccionado | str | nullable — plan que el cliente eligió |
| fecha_seleccion | datetime | nullable |
| num_turnos | int | default 0 — turnos de conversación |
| folio_contrato | str | nullable |

---

## Estructura de la app Streamlit

```
campaign_app/
├── app.py                        ← inicio / dashboard
├── pages/
│   ├── 1_Catalogo.py             ← familias, planes, beneficios, servicios, FAQs
│   ├── 2_Promociones.py          ← CRUD de promociones
│   ├── 3_Campanas.py             ← crear, configurar y gestionar campañas
│   ├── 4_Seguimiento.py          ← estado, interacciones, métricas
│   └── 5_Crear_desde_imagen.py   ← placeholder IA
├── db/
│   ├── models.py                 ← modelos SQLAlchemy
│   ├── database.py               ← conexión PostgreSQL
│   ├── crud.py                   ← operaciones CRUD
│   └── seed.py                   ← carga inicial desde plans.py y CSV
└── components/
    ├── catalog_forms.py          ← formularios reutilizables del catálogo
    ├── campaign_forms.py         ← formularios de campaña
    └── charts.py                 ← gráficas de seguimiento
```

### Páginas

#### Inicio (`app.py`)
Dashboard de acceso rápido: campañas activas, clientes contactados hoy, tasa de conversión global, accesos rápidos a crear campaña y ver seguimiento.

#### Catálogo (`1_Catalogo.py`)
Tabs internos:
- **Familias** — lista y formulario de edición
- **Planes** — tabla con todos los planes; editar precio, GB, cashback; toggle activo
- **Beneficios** — lista por familia; crear, editar, activar/desactivar
- **Servicios** — lista por familia; crear, editar, activar/desactivar
- **Preguntas Frecuentes** — lista con filtro por ámbito/beneficio/servicio; crear individual; importar desde Markdown

**Importación de FAQs desde Markdown:**
1. Uploader de archivo `.md`
2. Parser extrae pares pregunta/respuesta (detecta patrones: `##`/`###` como pregunta + párrafo siguiente, o bloques `Q:` / `A:`)
3. Vista de revisión — tabla editable: pregunta, respuesta, ámbito, selector de beneficio o servicio
4. Usuario selecciona cuáles importar con checkbox
5. "Insertar seleccionadas" — ninguna FAQ se graba sin confirmación

#### Promociones (`2_Promociones.py`)
Lista de promociones con badge de vigencia (activa / vencida / próxima). Formulario de creación/edición con editor JSON para `configuracion`. Toggle activo.

#### Campañas (`3_Campanas.py`)
Lista de campañas con filtro por estado. Al abrir una campaña, tres tabs:
- **Configuración** — nombre, descripción, vigencias, reglas de elegibilidad, planes disponibles + promoción por plan
- **Clientes** — carga CSV (valida columnas) o alta individual; selector de subconjunto; botón de envío; muestra conteo enviados/pendientes
- **Estado** — tabla de clientes con su estado de envío e interacción; reenvío solo a pendientes

**Lógica de envío:** al enviar, solo se procesan clientes con `estado_envio = pendiente`. Los ya enviados se saltan silenciosamente. Permite enviar al resto en cualquier momento sin afectar conversaciones activas.

#### Seguimiento (`4_Seguimiento.py`)
Tabla filtrable de `CampanaCliente` con columnas: línea, nombre, campaña, estado envío, estado interacción, plan seleccionado, turnos, folio. Métricas agregadas: enviados / en conversación / convertidos / rechazados. Gráfica de conversión por campaña.

#### Crear desde imagen (`5_Crear_desde_imagen.py`)
Uploader de imagen con mensaje "Próximamente: análisis automático vía IA". El hook de integración queda preparado en el componente para cuando se defina cómo llegará la información.

---

## Flujo de datos

```
Fase mock (esta fase):
  PostgreSQL ← interfaz Streamlit
  plans.py   → system_prompt.py → Reni   (sin cambio)

Fase producción (siguiente):
  PostgreSQL → (reemplaza plans.py) → system_prompt.py → Reni
```

**Seed script (`db/seed.py`):**
- Lee `CATALOG` y `FAMILY_BENEFITS` de `app/catalog/plans.py`
- Lee `docs/Masivo_clientes.csv`
- Inserta familias, planes, beneficios, servicios y clientes en la DB
- Idempotente — se puede correr varias veces sin duplicar

**Actualización desde Reni:** al finalizar cada turno en `reni_agent.py`, una llamada al CRUD actualiza `CampanaCliente`: incrementa `num_turnos`, actualiza `estado_interaccion`, registra `plan_seleccionado` y `folio_contrato` cuando aplica. Este ajuste es el único cambio al agente en esta fase.

**Visión final:** cambios de campaña (nuevos planes, promociones, segmentos) se hacen desde la interfaz. Solo las reglas de negocio (safety nets, detecciones pre-LLM) permanecen en código bajo responsabilidad del equipo de desarrollo.

---

## Manejo de errores

| Caso | Manejo |
|---|---|
| CSV con columnas faltantes | Validación antes de insertar — muestra columnas faltantes con mensaje claro |
| Línea duplicada en `Cliente` | `INSERT ... ON CONFLICT DO NOTHING` — reporta cuántos se ignoraron |
| Plan sin familia asignada | Campo requerido en formulario — no se guarda sin `familia_id` |
| FAQ importada sin categoría | `ambito = general` por defecto — el usuario la reasigna |
| Envío a cliente ya contactado | Verifica `estado_envio` antes de enviar — los ya enviados se saltan |
| Promoción con vigencia vencida | Badge visual "Vencida" en lista — no bloquea, solo advierte |
| JSON inválido en `configuracion` | Validación inline en el editor con mensaje de error antes de guardar |

---

## Testing

- **Seed script** como fixture de datos reales para prueba manual
- **Flujo manual:** crear campaña → cargar CSV → enviar a subconjunto → verificar que los ya enviados no se reenvían
- No se requieren tests automatizados en la fase de mock
