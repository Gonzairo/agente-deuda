import anthropic
from db import (leer_perfil, guardar_perfil_base, leer_instituciones,
                calcular_total_cuotas, guardar_historial, leer_vencimientos)
from config import MARGEN_MAX_PCT, ANTHROPIC_API_KEY
import re

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

META_AHORRO_DEFAULT = 0.15

MENSAJE_BIENVENIDA = """👋 Hola, soy tu asistente financiero personal.

Te ayudo a evaluar si puedes asumir un nuevo gasto o deuda.

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
   • mi ahorro → ver o cambiar tu meta de ahorro
   • eliminar [institución] → borrar una institución
   • registrar ingreso X gastos Y → actualizar tu perfil
   • registrar ingreso X gastos Y ahorro Z → con meta de ahorro personalizada"""

def construir_system_prompt(numero: str) -> str:
    perfil        = leer_perfil(numero)
    instituciones = leer_instituciones(numero)
    cuotas_total  = calcular_total_cuotas(numero)
    vencimientos  = leer_vencimientos(numero)

    if perfil and float(perfil.get("ingreso", 0)) > 0:
        ingreso          = float(perfil["ingreso"])
        gastos           = float(perfil["gastos"])
        meta_ahorro_pct  = float(perfil.get("meta_ahorro_pct") or META_AHORRO_DEFAULT)
        meta_ahorro      = ingreso * meta_ahorro_pct
        tope             = ingreso * MARGEN_MAX_PCT
        margen           = max(0.0, tope - cuotas_total)
        ingreso_lib      = ingreso - gastos - cuotas_total - meta_ahorro
        pct              = round(cuotas_total / ingreso * 100, 1)

        detalle = "\n".join(
            f"  - {r['institucion']} / {r['producto']}: ${float(r['cuota']):,.0f}/mes"
            for r in instituciones
        ) or "  (ninguna registrada)"

        facturados = {}
        for r in instituciones:
            inst = r["institucion"]
            if inst not in facturados and float(r.get("monto_facturado", 0)) > 0:
                facturados[inst] = float(r["monto_facturado"])
        detalle_facturado = "\n".join(
            f"  - {inst}: ${monto:,.0f}"
            for inst, monto in facturados.items()
        ) or "  (sin datos)"

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

        # Alerta si ingreso libre es bajo
        if ingreso_lib < 0:
            alerta_lib = f"⚠️ ATENCIÓN: con ahorro incluido el ingreso libre es NEGATIVO (${ingreso_lib:,.0f})"
        elif ingreso_lib < ingreso * 0.05:
            alerta_lib = f"⚠️ Ingreso libre muy ajustado: ${ingreso_lib:,.0f}/mes tras ahorro"
        else:
            alerta_lib = ""

        contexto = f"""
Perfil financiero del usuario:
- Ingreso neto mensual: ${ingreso:,.0f}
- Gastos fijos mensuales: ${gastos:,.0f}
- Meta de ahorro ({int(meta_ahorro_pct*100)}%): ${meta_ahorro:,.0f}/mes — es aporte patrimonial, NO un gasto
- Cuotas actuales ({pct}% del ingreso):
{detalle}
- Total cuotas: ${cuotas_total:,.0f}/mes
- Margen disponible para nueva deuda: ${margen:,.0f}/mes
- Ingreso libre real (tras gastos + cuotas + ahorro): ${ingreso_lib:,.0f}/mes
{alerta_lib}

Facturado último mes:
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

    return f"""Eres un asistente financiero personal por WhatsApp, especializado ÚNICAMENTE en evaluar si el usuario puede asumir un nuevo gasto o deuda.

{contexto}

Tu único propósito es responder preguntas como:
- ¿Puedo comprar X en Y cuotas?
- ¿Tengo margen para un crédito de $X?
- ¿Me conviene pagar en 6 o 12 cuotas?
- ¿Cuánto puedo gastar en cuotas este mes?

Reglas estrictas:
- Si la pregunta NO es sobre asumir un nuevo gasto o deuda → responde SOLO: "Solo puedo ayudarte a evaluar si puedes asumir un nuevo gasto o deuda. Pregúntame algo como: ¿puedo comprar X en Y cuotas?"
- NUNCA des consejos de inversión, ahorro, impuestos u otros temas
- NUNCA respondas preguntas fuera del ámbito de nuevos gastos o deudas
- NUNCA hagas preguntas de vuelta — solo analiza y responde

Reglas de cálculo:
- Tope saludable: {int(MARGEN_MAX_PCT*100)}% del ingreso en cuotas
- El ahorro es meta patrimonial — se muestra como contexto pero no bloquea la deuda
- Si una nueva cuota deja el ingreso libre bajo $0 después del ahorro → advertir aunque el % sea aceptable
- Cuota sin interés = precio ÷ cuotas
- Cuota con interés sin tasa → asume 18% anual, calcula cuota francesa

Formato de respuesta (siempre este orden):
1. SÍ / NO / DEPENDE en la primera línea
2. Cuota mensual calculada
3. Endeudamiento resultante en %
4. Ingreso libre tras ahorro
5. Una recomendación concreta de máximo 2 líneas

Formato WhatsApp: *negrita* para números clave, máximo 7 líneas en total."""

def registrar_perfil_desde_texto(numero: str, texto: str) -> str:
    def extraer(clave):
        m = re.search(rf"{clave}\s+([\d.,]+)", texto, re.IGNORECASE)
        return float(m.group(1).replace(".", "").replace(",", ".")) if m else None

    ingreso = extraer("ingreso")
    gastos  = extraer("gastos")
    ahorro  = extraer("ahorro")

    if not ingreso or gastos is None:
        return (
            "No pude leer los datos. Usa este formato:\n\n"
            "registrar ingreso 1500000 gastos 700000\n"
            "O con meta de ahorro personalizada:\n"
            "registrar ingreso 1500000 gastos 700000 ahorro 20"
        )

    # ahorro viene como porcentaje (ej: 20 → 0.20)
    if ahorro is not None:
        meta_ahorro_pct = ahorro / 100 if ahorro > 1 else ahorro
    else:
        meta_ahorro_pct = META_AHORRO_DEFAULT

    guardar_perfil_base(numero, ingreso, gastos, meta_ahorro_pct)

    tope        = ingreso * MARGEN_MAX_PCT
    cuotas      = calcular_total_cuotas(numero)
    margen      = max(0.0, tope - cuotas)
    meta_monto  = ingreso * meta_ahorro_pct

    return (
        f"Perfil registrado ✅\n\n"
        f"Ingreso neto: *${ingreso:,.0f}*\n"
        f"Gastos fijos: *${gastos:,.0f}*\n"
        f"Meta ahorro ({int(meta_ahorro_pct*100)}%): *${meta_monto:,.0f}/mes*\n"
        f"Margen disponible: *${margen:,.0f}/mes*\n\n"
        f"Sube tus estados de cuenta en PDF o pregúntame algo, ej:\n"
        f"_¿Puedo comprar un notebook de $900.000 en 12 cuotas?_"
    )

def mostrar_ahorro(numero: str) -> str:
    perfil = leer_perfil(numero)
    if not perfil or not float(perfil.get("ingreso", 0)):
        return "No tienes perfil registrado. Usa: registrar ingreso X gastos Y"
    ingreso         = float(perfil["ingreso"])
    meta_ahorro_pct = float(perfil.get("meta_ahorro_pct") or META_AHORRO_DEFAULT)
    meta_monto      = ingreso * meta_ahorro_pct
    return (
        f"Tu meta de ahorro actual: *{int(meta_ahorro_pct*100)}%* = *${meta_monto:,.0f}/mes*\n\n"
        f"Para cambiarla escribe:\n"
        f"registrar ingreso {int(ingreso)} gastos {int(float(perfil['gastos']))} ahorro 20\n"
        f"(reemplaza 20 por el % que quieras)"
    )

def procesar_mensaje(numero: str, texto: str, historial: list[dict]) -> str:
    if texto.lower().startswith("registrar"):
        return registrar_perfil_desde_texto(numero, texto)

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
