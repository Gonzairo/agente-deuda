# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WhatsApp financial AI agent that helps users track and manage personal debts. Built with FastAPI + Twilio + Claude API + Supabase. Users send messages (or PDF bank statements) to a WhatsApp number; the agent extracts debt data, stores it, and provides personalized financial advice.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (port 8000)
uvicorn main:app --reload

# Expose locally for Twilio webhook testing
ngrok http 8000
# Set Twilio webhook to: https://<ngrok-url>/webhook

# Health check
curl http://localhost:8000/health
```

Deployment uses `Procfile.txt`:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

No test suite or linter is configured.

## Architecture

### Request Flow

```
Twilio WhatsApp → POST /webhook (main.py)
  ├─ PDF attachment → descargar_pdf() → extraer_y_guardar_eecc() (pdf_parser.py)
  │     └─ Claude vision extracts debt data → guardar_instituciones() (db.py)
  ├─ "mis deudas" → leer_instituciones() → formatted list
  ├─ "eliminar [institución]" → eliminar_institucion() (db.py)
  ├─ "registrar ingreso X gastos Y" → registrar_perfil_desde_texto() (agent.py)
  └─ free text → procesar_mensaje() (agent.py)
        └─ construir_system_prompt() + last 10 messages → Claude → response
              └─ guardar_historial() (db.py)
→ MessagingResponse (TwiML) → Twilio → WhatsApp user
```

### Key Financial Logic

All logic lives in `agent.py`:
- Healthy debt ceiling: `margen = (ingreso * 0.35) - cuotas_total` (configurable via `MARGEN_MAX_PCT`)
- Debt percentage: `(cuotas_total / ingreso) * 100`
- Available cash: `ingreso - gastos - cuotas_total`

`construir_system_prompt()` injects the user's full financial profile (income, expenses, all debts, margin) into every Claude call so responses are personalized.

### Key Files

| File | Responsibility |
|------|---------------|
| `main.py` | FastAPI webhook, command routing, in-memory conversation history (`historiales` dict) |
| `agent.py` | Claude chat integration, system prompt builder, `registrar` command parser |
| `pdf_parser.py` | Download PDF from Twilio, send to Claude vision, parse JSON debt extraction |
| `db.py` | All Supabase reads/writes (perfil, instituciones, historial) |
| `config.py` | Loads all env vars from `.env` |

### Supabase Tables

- `perfil` — `(numero PK, ingreso, gastos, fecha)` — one row per WhatsApp number
- `instituciones` — `(numero, institucion, producto, cuota, fecha)` — one row per debt product
- `historial` — `(numero, mensaje, respuesta, fecha)` — conversation log

### PDF Parsing

`pdf_parser.py` encodes the PDF as base64 and asks Claude to return structured JSON:
```json
{
  "institucion": "Banco X",
  "periodo": "2025-03",
  "productos": [{"nombre": "...", "cuota_mensual": 50000, ...}]
}
```
Only installment payments (`cuota_mensual`) are extracted — revolving credit card balances are intentionally ignored.

### Conversation Context

Conversation history is stored **in memory** (`historiales` dict in `main.py`) and lost on restart. The last 10 messages are sent to Claude on each request. All turns are also persisted to the `historial` Supabase table.

## Environment Variables

```
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_NUMBER          # whatsapp:+...
SUPABASE_URL
SUPABASE_KEY
ANTHROPIC_API_KEY
MARGEN_MAX_PCT         # default 0.35 (35% debt ceiling)
```

## Claude Usage

Two separate Claude calls, both using `claude-sonnet-4-20250514`:
1. **Chat** (`agent.py`) — `max_tokens=400`, financial advisor persona with injected user context
2. **PDF vision** (`pdf_parser.py`) — `max_tokens=1000`, document analysis returning structured JSON

Number format in Chile uses `.` as thousands separator and `,` as decimal — `agent.py` normalizes this with regex before parsing.
