from fastapi import FastAPI, Response, Request
from twilio.twiml.messaging_response import MessagingResponse
from agent import procesar_mensaje, registrar_perfil_desde_texto
from pdf_parser import descargar_pdf, extraer_y_guardar_eecc
from db import leer_instituciones, calcular_total_cuotas, eliminar_institucion
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from itertools import groupby

app = FastAPI()
historiales: dict[str, list[dict]] = {}

@app.post("/webhook")
async def webhook(request: Request):
    form      = await request.form()
    numero    = form.get("From", "").replace("whatsapp:", "")
    texto     = form.get("Body", "").strip()
    num_media = int(form.get("NumMedia", 0))
    twiml     = MessagingResponse()

    print(f"DEBUG numero: {numero}")
    print(f"DEBUG texto: {texto}")
    print(f"DEBUG num_media: {num_media}")

    # — PDF adjunto —
    if num_media > 0:
        media_url          = form.get("MediaUrl0", "")
        media_content_type = form.get("MediaContentType0", "")

        print(f"DEBUG media_url: {media_url}")
        print(f"DEBUG media_content_type: {media_content_type}")

        es_pdf = (
            "pdf" in media_content_type or
            "octet-stream" in media_content_type or
            media_url.lower().endswith(".pdf")
        )

        if es_pdf:
            try:
                pdf_bytes = descargar_pdf(media_url, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                print(f"DEBUG pdf_bytes size: {len(pdf_bytes)}")
                datos     = extraer_y_guardar_eecc(pdf_bytes, numero)
                productos = datos.get("productos", [])
                detalle   = "\n".join(
                    f"  • {p['nombre']}: *${p['cuota_mensual']:,}*/mes"
                    for p in productos if p.get("cuota_mensual")
                )
                total     = calcular_total_cuotas(numero)
                respuesta = (
                    f"_{datos.get('institucion')} — {datos.get('periodo', '')}_\n"
                    f"{detalle}\n\n"
                    f"Total acumulado: *${total:,.0f}/mes* ✅"
                )
            except Exception as e:
                print(f"ERROR procesando PDF: {e}")
                import traceback
                traceback.print_exc()
                respuesta = f"No pude leer el PDF. Error: {str(e)[:100]}"
        else:
            respuesta = (
                f"Recibí un archivo de tipo: {media_content_type}\n"
                f"Por ahora solo proceso PDFs. Envía tu estado de cuenta en PDF."
            )

        twiml.message(respuesta)
        return Response(content=str(twiml), media_type="application/xml")

    # — Comandos de texto —
    texto_lower = texto.lower()

    if texto_lower == "mis deudas":
        instituciones = leer_instituciones(numero)
        if not instituciones:
            respuesta = "No tienes instituciones registradas. Sube un PDF para comenzar."
        else:
            lineas = []
            key = lambda r: r["institucion"]
            for inst, items in groupby(sorted(instituciones, key=key), key=key):
                items    = list(items)
                subtotal = sum(float(i["cuota"]) for i in items)
                lineas.append(f"*{inst}* — ${subtotal:,.0f}/mes")
                for i in items:
                    lineas.append(f"  · {i['producto']}: ${float(i['cuota']):,.0f}")
            total = calcular_total_cuotas(numero)
            lineas.append(f"\nTotal: *${total:,.0f}/mes*")
            respuesta = "\n".join(lineas)

    elif texto_lower.startswith("eliminar "):
        inst = texto[9:].strip()
        eliminar_institucion(numero, inst)
        total     = calcular_total_cuotas(numero)
        respuesta = f"_{inst}_ eliminado ✅\nNuevo total: *${total:,.0f}/mes*"

    elif texto_lower.startswith("registrar"):
        respuesta = registrar_perfil_desde_texto(numero, texto)

    else:
        if numero not in historiales:
            historiales[numero] = []
        respuesta = procesar_mensaje(numero, texto, historiales[numero])
        historiales[numero].append({"role": "user",      "content": texto})
        historiales[numero].append({"role": "assistant",  "content": respuesta})

    twiml.message(respuesta)
    return Response(content=str(twiml), media_type="application/xml")

@app.get("/health")
def health():
    return {"status": "ok"}
