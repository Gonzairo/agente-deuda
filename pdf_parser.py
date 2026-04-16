import anthropic
import httpx
import base64
import json
import re
from db import guardar_instituciones
from config import ANTHROPIC_API_KEY

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
        model="claude-sonnet-4-5",
        max_tokens=1000,
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
  "productos": [
    {
      "nombre": "descripción del producto",
      "cuota_mensual": 150000,
      "saldo_pendiente": 900000,
      "cuotas_restantes": 6
    }
  ],
  "total_cuotas_mensuales": 150000
}

Reglas:
- Solo cuotas o pagos mínimos que debe pagar este mes
- Ignora saldo rotativo de tarjeta de crédito
- Montos como enteros sin puntos ni símbolos
- Si hay múltiples productos con cuota inclúyelos todos"""
                }
            ],
        }],
    )

    texto = response.content[0].text.strip()
    print(f"DEBUG Claude respuesta: {texto[:300]}")

    # Limpiar backticks si el modelo los incluye
    texto = texto.replace("```json", "").replace("```", "").strip()

    # Extraer JSON aunque venga con texto alrededor
    match = re.search(r'\{.*\}', texto, re.DOTALL)
    if not match:
        raise ValueError(f"Sin JSON válido: {texto[:200]}")

    datos = json.loads(match.group())
    guardar_instituciones(numero, datos["institucion"], datos["productos"])
    return datos

