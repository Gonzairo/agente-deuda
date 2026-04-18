import anthropic
import httpx
import base64
import json
import re
from db import guardar_instituciones, guardar_vencimientos
from config import ANTHROPIC_API_KEY, MODEL

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def descargar_pdf(url: str, twilio_sid: str, twilio_token: str) -> bytes:
    response = httpx.get(
        url,
        auth=(twilio_sid, twilio_token),
        follow_redirects=True
    )
    response.raise_for_status()
    return response.content

def extraer_y_guardar_eecc(pdf_bytes: bytes, numero: str) -> dict:
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {
                    "type": "text",
                    "text": """Analiza este estado de cuenta bancario o de retail chileno.

Responde ÚNICAMENTE con JSON válido, sin texto adicional, sin backticks:

{
  "institucion": "nombre exacto del banco o institución",
  "periodo": "mes/año del estado de cuenta",
  "monto_total_facturado": 5839046,
  "monto_minimo_pagar": 274979,
  "productos": [
    {
      "nombre": "descripción del producto",
      "cuota_mensual": 86443,
      "saldo_pendiente": 1555980,
      "cuotas_restantes": 2
    }
  ],
  "total_cuotas_mensuales": 275186,
  "vencimientos_proximos": {
    "mes_1": 275186,
    "mes_2": 275186,
    "mes_3": 188743,
    "mes_4": 160648
  }
}

Reglas:
- En "productos" incluye SOLO transacciones en cuotas (créditos, compras en cuotas)
- NO incluyas gastos en una cuota (Netflix, Uber, supermercado, etc.)
- NO incluyas intereses ni comisiones en productos
- "monto_total_facturado" es el total a pagar este mes
- "monto_minimo_pagar" es el pago mínimo indicado
- "vencimientos_proximos" son las cuotas de los próximos 4 meses si aparecen
- Si no hay vencimientos próximos usa null
- Montos como enteros sin puntos ni símbolos"""
                }
            ],
        }],
    )

    texto = response.content[0].text.strip()
    print(f"DEBUG Claude respuesta: {texto[:300]}")

    texto = texto.replace("```json", "").replace("```", "").strip()

    match = re.search(r'\{.*\}', texto, re.DOTALL)
    if not match:
        raise ValueError(f"Sin JSON válido: {texto[:200]}")

    datos = json.loads(match.group())

    guardar_instituciones(
        numero,
        datos["institucion"],
        datos["productos"],
        monto_facturado=datos.get("monto_total_facturado", 0),
        monto_minimo=datos.get("monto_minimo_pagar", 0)
    )

    if datos.get("vencimientos_proximos"):
        guardar_vencimientos(numero, datos["institucion"], datos["vencimientos_proximos"])

    return datos
