import anthropic
from db import (leer_perfil, guardar_perfil_base, leer_instituciones,
                calcular_total_cuotas, guardar_historial, leer_vencimientos)
from config import MARGEN_MAX_PCT, ANTHROPIC_API_KEY
import re

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MENSAJE_BIENVENIDA = """👋 Hola, soy tu asistente financiero personal.

Te ayudo a saber cuánto margen tienes para endeudarte.

*Para empezar necesito dos cosas:*

1️⃣ *Tu perfil base* — escríbeme:
   registrar ingreso 1500000 gastos 700000
   (ingreso neto + gastos fijos sin contar deudas)

2️⃣ *Tus estados de cuenta* — adjunta tus PDFs de:
   • Tarjetas de crédito
   • Créditos de consumo
   • Cualquier deuda bancaria o retail

*Una vez que tenga tus datos puedes preguntarme:*
   _¿Puedo comprar un auto de $8.000.000 en 48 cuotas?_
   _¿Cuánto margen me queda para endeudarme?_
   _¿Conviene pagar en 6 o 12 cuotas?_

*Comandos útiles:*
   • mis deudas → ver resumen de tus cuotas actuales
   • eliminar [institución] → borrar una institución
   • registrar ingreso X gastos Y → actualizar tu perfil"""

def construir_system_prompt(numero: str) -> str:
    perfil        = leer_perfil(numero)
    instituciones = leer_instituciones(numero)
    cuotas_total  = calcular_total_cuotas(numero)
    vencimientos  = leer_vencimientos(numero)

    if perfil and float(perfil.get("ingreso", 0)) > 0:
        ingreso     = float(perfil["ingreso"])
        gastos      = float(perfil["gastos"])
        tope        = ingreso * MARGEN_MAX_PCT
        margen      = max(0.0, tope - cuotas_total)
        ingreso_lib = ingreso - gastos - cuotas_total
        pct         = round(cuotas_total / ingreso * 100, 1)

        detalle = "\n".join(
            f"  - {r['institucion']} / {r['producto']}: ${float(r['cuota']):,.0f}/mes"
            f" (faltan {r.get('cuotas_restantes', '?')} cuotas)"
            for r in instituciones
        ) or "  (ninguna registrada)"

        # Facturado por institución
        facturados = {}
        for r in instituciones:
            inst = r["institucion"]
            if inst not in facturados and float(r.get("monto_facturado", 0)) > 0:
                facturados[inst] = float(r["monto_facturado"])
        detalle_facturado = "\n".join(
            f"  - {inst}: ${monto:,.0f}"
            for inst, monto in facturados.items()
        ) or "  (sin datos)"

        # Vencimientos próximos
        if vencimientos:
            lineas_venc = []
            for v in vencimientos:
                lineas_venc.append(
                    f"  {v['institucion']}: "
                    f"mes1=${float(v['mes_1']):,.0f} | "
                    f"mes2=${float(v['mes_2']):,.0f} | "
                    f"mes3=${float(v['mes_3']):,.0f} | "
                    f"mes4=${float(v['mes_4']):,.0f}"
                )
            contexto_venc = "Vencimientos próximos 4 meses:\n" + "\n".join(lineas_venc)
        else:
            contexto_venc = ""

        contexto = f"""
Perfil financiero del usuario:
- Ingreso neto mensual: ${ingreso:,.0f}
- Gastos fijos mensuales: ${gastos:,.0f}
- Cuotas actuales ({pct}% del ingreso):
{detalle}
- Total cuotas: ${cuotas_total:,.0f}/mes
- Margen disponible para nueva deuda: ${margen:,.0f}/mes
- Ingreso libre tras todo: ${ingreso_lib:,.0f}/mes

Facturado último mes por institución:
{detalle_facturado}

{contexto_venc}
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
- Considera vencimientos próximos para dar recomendaciones temporales
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

    # Primera interacción sin perfil → bienvenida
    if not historial:
        perfil = leer_perfil(numero)
        if not perfil:
            guardar_historial(numero, texto, MENSAJE_BIENVENIDA)
            return MENSAJE_BIENVENIDA

    system   = construir_system_prompt(numero)
    messages = historial[-10:] + [{"role": "user", "content": texto}]

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        system=system,
        messages=messages
    )

    respuesta = response.content[0].text
    guardar_historial(numero, texto, respuesta)
    return respuesta
