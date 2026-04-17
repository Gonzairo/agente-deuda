from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY
from datetime import datetime

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def leer_perfil(numero: str) -> dict | None:
    r = get_db().table("perfil").select("*").eq("numero", numero).execute()
    return r.data[0] if r.data else None

def guardar_perfil_base(numero: str, ingreso: float, gastos: float):
    get_db().table("perfil").upsert({
        "numero":  numero,
        "ingreso": ingreso,
        "gastos":  gastos,
        "fecha":   datetime.now().isoformat()
    }).execute()

def leer_instituciones(numero: str) -> list[dict]:
    r = get_db().table("instituciones").select("*").eq("numero", numero).execute()
    return r.data or []

def guardar_instituciones(numero: str, institucion: str, productos: list[dict],
                          monto_facturado: float = 0, monto_minimo: float = 0):
    db = get_db()
    db.table("instituciones")\
      .delete()\
      .eq("numero", numero)\
      .eq("institucion", institucion)\
      .execute()
    rows = [
        {
            "numero":           numero,
            "institucion":      institucion,
            "producto":         p.get("nombre", "Sin nombre"),
            "cuota":            p["cuota_mensual"],
            "monto_facturado":  monto_facturado,
            "monto_minimo":     monto_minimo,
            "fecha":            datetime.now().isoformat()
        }
        for p in productos if p.get("cuota_mensual")
    ]
    if rows:
        db.table("instituciones").insert(rows).execute()

def calcular_total_cuotas(numero: str) -> float:
    instituciones = leer_instituciones(numero)
    return sum(float(r.get("cuota", 0)) for r in instituciones)

def eliminar_institucion(numero: str, institucion: str):
    db = get_db()
    db.table("instituciones")\
      .delete()\
      .eq("numero", numero)\
      .ilike("institucion", institucion)\
      .execute()
    db.table("vencimientos")\
      .delete()\
      .eq("numero", numero)\
      .ilike("institucion", institucion)\
      .execute()

def guardar_vencimientos(numero: str, institucion: str, vencimientos: dict):
    db = get_db()
    db.table("vencimientos").delete()\
      .eq("numero", numero)\
      .eq("institucion", institucion)\
      .execute()
    db.table("vencimientos").insert({
        "numero":      numero,
        "institucion": institucion,
        "mes_1":       vencimientos.get("mes_1", 0),
        "mes_2":       vencimientos.get("mes_2", 0),
        "mes_3":       vencimientos.get("mes_3", 0),
        "mes_4":       vencimientos.get("mes_4", 0),
        "fecha":       datetime.now().isoformat()
    }).execute()

def leer_vencimientos(numero: str) -> list[dict]:
    r = get_db().table("vencimientos").select("*").eq("numero", numero).execute()
    return r.data or []

def guardar_historial(numero: str, mensaje: str, respuesta: str):
    get_db().table("historial").insert({
        "numero":    numero,
        "mensaje":   mensaje,
        "respuesta": respuesta,
        "fecha":     datetime.now().isoformat()
    }).execute()
