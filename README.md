# ReniAgent — Strands Agents + OCI Generative AI

Agente de ventas Telcel migrado de LangGraph a **Strands Agents**, usando
**OCI Generative AI (Llama)** como modelo via LiteLLM.

## Estructura

```
reni-strands-agent/
├── app/
│   ├── agent/          # Definición del agente Strands
│   ├── config/         # Configuración de OCI y variables de entorno
│   ├── prompts/        # System prompt y reglas del agente
│   ├── state/          # Estado conversacional
│   └── tools/          # Herramientas del agente (se irán añadiendo)
├── docs/               # Documentación de reglas y flujo
├── main.py             # Entry point FastAPI
├── pyproject.toml
└── .env.example
```

## Setup

```bash
pip install strands-agents strands-agents-tools litellm fastapi uvicorn python-dotenv
```

Copia `.env.example` a `.env` y rellena tus credenciales OCI.

## Ejecutar

```bash
uvicorn main:app --reload
```

## Fases de construcción

- [x] **Fase 1** — Base: estructura, config OCI, identidad y reglas generales
- [ ] **Fase 2** — Router: clasificación de intenciones
- [ ] **Fase 3** — Persuasion: recomendación y manejo de objeciones
- [ ] **Fase 4** — Contract: confirmación y autenticación
- [ ] **Fase 5** — Post-sale: entrega de folio y cierre
