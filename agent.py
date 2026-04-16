import anthropic
from db import (leer_perfil, guardar_perfil_base, leer_instituciones,
                calcular_total_cuotas, guardar_historial)
from config import MARGEN_MAX_PCT, ANTHROPIC_API_KEY
import re

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def construir_system_prompt(numero: str) -> str:
    perfil        = leer_perfil(numero)
    instituciones = leer_instituciones(numero)
    cuotas_total  = calcular_total_cuotas(numero)

    if perfil and float(perfil.get("ingreso", 0)) > 0:
        ingreso     = float(perfil["ingreso"])
        gastos      = float(perfil["gastos"])
        tope        = ingreso * MARGEN_MAX_PCT
        margen      = max(0.0, tope - cuotas_total)
        ingreso_lib = ingreso - gastos - cuotas_total
        pct         = round(cuotas_total / ingreso * 100, 1)

        detalle = "\n".join(
            f"  - {r['institucion']} / {r['producto']}: ${float(r['cuota']):,.0f}/mes"
            for r in instituciones
        ) or "  (ninguna registrada)"

        contexto = f"""
Perfil financiero del usuario:
- Ingreso neto mensual: ${ingreso:,.0f}
- Gastos fijos mensuales: ${gastos:,.0f}
- Cuotas actuales ({pct}% del ingreso):
{detalle}
- Total cuotas: ${cuotas_total:,.0f}/mes
- Margen disponible para nueva deuda: ${margen:,.0f}/mes
- Ingreso libre tras todo: ${ingreso_lib:,.0f}/mes
"""
    else:
        contexto = """
No hay perfil financiero registrado.
Pídele que registre su ingreso y gastos con:
  registrar ingreso 1500000 gastos 700000
Y que suba sus estados de cuenta en PDF.
"""

    return f"""Eres un asistente financiero personal por WhatsApp. Respuestas cortas y directas.

{contexto}

Comandos que el usuario puede usar:
- Enviar PDF → procesas el estado de cuenta
- "mis deudas" → resumen de todas sus instituciones
- "eliminar [institución]" → borra esa institución
- "registrar ingreso X gastos Y" → actualiza perfil base

Reglas de cálculo:
- Tope saludable: {int(MARGEN_MAX_PCT*100)}% del ingreso en cuotas
- Cuota sin interés = precio ÷ cuotas
- Cuota con interés sin tasa → asume 18% anual, calcula cuota francesa
- Muestra siempre: cuota calculada, % endeudamiento resultante, recomendación

Formato WhatsApp: *negrita* para números clave, máximo 6 líneas."""

def registrar_perfil_desde_texto(numero: str, texto: str) -> str:
    def extraer(clave):
        m = re.search(rf"{clave}\s+([\d.,]+)", texto, re.IGNORECASE)
        return float(m.group(1).replace(".", "").replace(",", ".")) if m else None

    ingreso = extraer("ingreso")
    gastos  = extraer("gastos")

    if not ingreso or gastos is None:
        return (
            "No pude leer los datos. Usa este formato:\n\n"
            "registrar ingreso 1500000 gastos 700000"
        )

    guardar_perfil_base(numero, ingreso, gastos)
    tope   = ingreso * MARGEN_MAX_PCT
    cuotas = calcular_total_cuotas(numero)
    margen = max(0.0, tope - cuotas)

    return (
        f"Perfil registrado ✅\n\n"
        f"Ingreso neto: *${ingreso:,.0f}*\n"
        f"Gastos fijos: *${gastos:,.0f}*\n"
        f"Margen disponible: *${margen:,.0f}/mes*\n\n"
        f"Ahora sube tus estados de cuenta en PDF o pregúntame algo, ej:\n"
        f"_¿Puedo comprar un notebook de $900.000 en 12 cuotas?_"
    )

def procesar_mensaje(numero: str, texto: str, historial: list[dict]) -> str:
    if texto.lower().startswith("registrar"):
        return registrar_perfil_desde_texto(numero, texto)

    system   = construir_system_prompt(numero)
    messages = historial[-10:] + [{"role": "user", "content": texto}]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        system=system,
        messages=messages
    )

    respuesta = response.content[0].text
    guardar_historial(numero, texto, respuesta)
    return respuesta