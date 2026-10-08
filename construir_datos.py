"""Encuestas 419 (Hogar) y 508 (Móvil) de Factura, pago y cobro: Oracle -> tablero/datos.json, sin PII.

Uso: /opt/apps/claro_agente_ai/.venv/bin/python construir_datos.py

Lee INVITADO_15.TBL_ENC_FACT_PAGOS_COBROS en una transacción de solo lectura (credenciales en `.env`:
ORACLE_HOST, ORACLE_PORT, ORACLE_USER, ORACLE_PASSWORD, ORACLE_DBNAME). Solo se piden las columnas que
usa el tablero: nombre, identificación, cuenta, teléfono y `OBSERVACION` no salen de la base.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

import oracledb
import pandas as pd

AQUI = Path(__file__).parent
TABLA = "INVITADO_15.TBL_ENC_FACT_PAGOS_COBROS"
SALIDA = AQUI / "tablero" / "datos.json"

MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}

# columna de Oracle -> nombre corto en el JSON
NUM = {
    "p1": "P1_SATISFACCION_FACTURA",
    "p2": "P2_FACILIDAD_ENTENDER",
    "p5": "P5_SATISFACCION_PAGO",
    "p6": "P6_FACILIDAD_PAGO",
    "p7": "P7_CLARIDAD_PAGO",
    "p9": "P9_SATISFACCION_COBRO",
    "nps": "P11_RECOMENDACION_NPS",
}
SINO = {
    "p3": "P3_VALORES_ACORDES_PLAN",
    "p4": "P4_TIEMPO_SUFICIENTE_REVISAR",
    "p8": "P8_RECIBIO_RECORDATORIOS",
}
CAT = {
    "neg": "TIPO_BASE", "region": "REGION", "ciudad": "CIUDAD", "base": "BASE_ORIGEN", "canal": "DES_CANAL",
    "m11": "P1_1_MOTIVO_CALIF",
    "m12": "P1_2_MOTIVO_CALIF",
    "m21": "P2_1_DETALLE_DIFICIL",
    "m31": "P3_1_CONCEPTOS_ERRONEOS",
    "m51": "P5_1_MOTIVO_CALIF",
    "m61": "P6_1_DETALLE_DIFICIL",
    "m71": "P7_1_ASPECTO_ERRADO_1",
    "m72": "P7_2_MOTIVO_FALTA_CLARIDAD",
    "m91": "P9_1_MOTIVO_CALIF",
    "a10": "P10_EMOCIONES_PROCESO",
    "e10": "P10_2_EMOCIONES",
    "m112": "P11_2_MOTIVO_CALIF",
}
# Texto abierto. `OBSERVACION` queda fuera a propósito: trae el nombre de quien contesta.
VERB = {
    "nps": "P11_2_OTRO", "proc": "P10_1_OTRO", "fac": "P2_2_DETALLE_DIFICIL",
    "val": "P3_2_PROFUNDIZACION", "pag": "P5_2_MOTIVO_CALIF",
    "dif": "P6_2_DETALLE_DIFICIL", "cob": "P9_1_OTRO",
    "cla": "P7_1_OTRO_CUAL",
}
VACIOS = {"", "n/a", "na", "ninguna", "ninguno", "no", "nada", "sin divisional"}
# únicas columnas que se piden a Oracle (las de chequeo incluidas)
USADAS = ["REGISTRO_ID", "MES_ENCUESTA", "FECHA_HORA_GESTION", "DES_MEDIO", "NPS", "SAT", "ESF", "ESF_PAGO", "SAT_COBRO",
          *NUM.values(), *SINO.values(), *CAT.values(), *VERB.values()]
# Móvil trae el canal de pago en DES_CANAL o en DES_MEDIO según la fila (BANCO/NEQUI y NEQUI/BANCO):
# se toma el genérico de los dos. Hogar no trae DES_MEDIO y usa DES_CANAL tal cual.
CANALES = {"BANCO", "DOMICILIADO", "CAV - CPS", "BOTON DE PAGOS DEBITO", "BOTON DE PAGOS CREDITO",
           "PAGO POR ANTICIPADO", "RED MULTICOLOR", "SIN IDENTIFICAR"}
DIGITOS = re.compile(r"\d(?:[\s.,-]?\d){4,}")  # cédulas, cuentas, teléfonos (y de paso montos largos)
MAYUS = {"Region": "Región", "Bogota": "Bogotá", "Medellin": "Medellín", "Movil": "Móvil", "Nomina": "Nómina",
         "Boton": "Botón", "Debito": "Débito", "Credito": "Crédito", "Cav": "CAV", "Cps": "CPS"}
NOMBRES = {"FACT HOGAR": "Facturación", "COBRANZA HOGAR": "Cobranza", "FACT MOVIL": "Facturación",
           "COBRANZA MOVIL": "Cobranza", "HOGAR": "Hogar", "MOVIL": "Móvil", "BOGOTA DC": "Bogotá D.C."}
# mojibake y variantes que llegan así de la fuente
CIUDADES = {"Medellã\x8dN": "Medellín", "Ansermaâ": "Anserma", "Caucasiaâ": "Caucasia", "Oca#A": "Ocaña",
            "San Jose De La Monta#A": "San José de la Montaña", "Dos Quebradas": "Dosquebradas",
            "Magdalena-Guajira": "Magdalena Guajira", "Villa De San Diego De Uba": "Villa De San Diego De Ubate",
            "Centr-47-02 Fttactotran604 644Bel6Bm6Bmp": None, "Sin Municipio": None, "Sin Zona": None,
            "Sin Departamento": None, "Territorios Nac": "Territorios Nacionales", "Regional Orient": "Regional Oriente",
            "Santamarta": "Santa Marta"}


def limpiar(s):
    if not isinstance(s, str):
        return None
    s = re.sub(r"\s+", " ", s).strip().replace("Otro ¿Cúal?", "Otro")
    return None if s.lower() in VACIOS else s


def canonizar(tabla):
    """Unifica variantes que solo difieren en mayúsculas/espacios (en todas las columnas a la vez,
    p. ej. 'Gestión de Pagos' vs 'Gestión de pagos'): se queda la forma más frecuente."""
    tabla = tabla.apply(lambda c: c.map(limpiar))
    todo = tabla.stack().dropna()
    forma = todo.groupby(todo.str.casefold()).agg(lambda x: x.value_counts().index[0])
    return tabla.apply(lambda c: c.map(lambda v: forma[v.casefold()] if isinstance(v, str) else None))


def bonito(v):
    """'REGION NOROCCIDENTE' -> 'Noroccidente', 'FACT HOGAR' -> 'Facturación'."""
    if not isinstance(v, str):
        return None
    v = NOMBRES.get(v, v)
    if v.isupper():
        v = " ".join(MAYUS.get(w, w) for w in v.title().split())
    if v.startswith(("Bogota", "Bogotá", "Santafe De Bogo")):
        return "Bogotá D.C."
    return CIUDADES.get(v, v)


def verbatim(s):
    s = limpiar(s)
    if not s or len(s) < 6:
        return None
    s = DIGITOS.sub("[#]", s)
    return s[0].upper() + s[1:]


def consultar(columnas):
    """Esas columnas de TABLA, en una transacción de solo lectura (con los `_x000D_` de Excel ya como \\r)."""
    for linea in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
        k, _, v = linea.partition("=")
        if v and not k.strip().startswith("#"):
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    e = os.environ
    with oracledb.connect(user=e["ORACLE_USER"], password=e["ORACLE_PASSWORD"], host=e["ORACLE_HOST"],
                          port=int(e["ORACLE_PORT"]), service_name=e["ORACLE_DBNAME"]) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(f"SELECT {', '.join(dict.fromkeys(columnas))} FROM {TABLA} ORDER BY TIPO_BASE, FECHA_HORA_GESTION, REGISTRO_ID")
        df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    return df.replace("_x000D_", "\r", regex=True)  # la carga desde Excel dejó los \r así


def cargar():
    df = consultar(USADAS)
    df["DES_CANAL"] = df["DES_CANAL"].where(df["DES_MEDIO"].isna() | df["DES_CANAL"].isin(CANALES), df["DES_MEDIO"])
    df["REGION"] = df["REGION"].str.replace(r"^REGION\s*", "", regex=True)  # Móvil trae 'REGIONORIENTE'
    for neg, d in df.groupby("TIPO_BASE"):
        print(f"{neg}: {len(d)} encuestas, {d['FECHA_HORA_GESTION'].min():%Y-%m-%d} a {d['FECHA_HORA_GESTION'].max():%Y-%m-%d}")
    return df


def construir(df):
    num = df["MES_ENCUESTA"].astype(str).str.strip().str.lower().map(MESES)
    if num.isna().any():
        raise SystemExit(f"Mes no reconocido: {sorted(df.loc[num.isna(), 'MES_ENCUESTA'].astype(str).unique())}")
    fecha = pd.to_datetime(df["FECHA_HORA_GESTION"])
    anio = fecha.dt.year - (num > fecha.dt.month)  # encuesta de diciembre gestionada en enero
    out = pd.DataFrame({"mes": anio.astype(str) + "-" + num.astype(int).map("{:02d}".format)})
    out["fecha"] = fecha.dt.day
    for k, c in NUM.items():
        out[k] = pd.to_numeric(df[c].astype(str).str.strip(), errors="coerce")
    for k, c in SINO.items():
        out[k] = df[c].str.strip().map({"Si": 1, "No": 0})
    out[list(CAT)] = canonizar(df[list(CAT.values())].set_axis(list(CAT), axis=1))
    for k in ("neg", "region", "ciudad", "base", "canal"):
        out[k] = out[k].map(bonito)

    # diccionario único de categorías -> índices (el JSON pesa mucho menos)
    dic = sorted({v for k in CAT for v in out[k].dropna().unique()})
    idx = {v: i for i, v in enumerate(dic)}
    campos = ["mes", "fecha", *NUM, *SINO, *CAT]
    filas = []
    for i, r in out.iterrows():
        fila = []
        for k in campos:
            v = r[k]
            if pd.isna(v):
                fila.append(None)
            elif k in CAT:
                fila.append(idx[v])
            elif k == "mes":
                fila.append(v)
            else:
                fila.append(int(v))
        vs = {}
        for k, c in VERB.items():
            t = verbatim(df.at[i, c])
            if t and t not in vs.values():
                vs[k] = t
        fila.append(vs or None)
        filas.append(fila)

    return {
        "meta": {
            "estudio": "419 Hogar y 508 Móvil · Factura, pago y cobro",
            "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "n": len(filas),
            "meses": sorted(out["mes"].unique()),
        },
        "campos": campos + ["v"],
        "dic": dic,
        "filas": filas,
    }


if __name__ == "__main__":
    df = cargar()
    d = construir(df)
    texto = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(texto, encoding="utf-8")

    # auto-chequeo: lo calculado debe cuadrar con las columnas ya clasificadas de la propia base
    c = {k: i for i, k in enumerate(d["campos"])}
    f = d["filas"]
    n = len(f)
    t = lambda col: df[col].astype(str).str.strip()
    pro = sum(r[c["nps"]] >= 9 for r in f)
    det = sum(r[c["nps"]] <= 6 for r in f)
    assert n == len(df) and not df.duplicated(["TIPO_BASE", "REGISTRO_ID"]).any(), "encuestas duplicadas o perdidas"
    assert (pro, det) == ((t("NPS") == "Promotor").sum(), (t("NPS") == "Detractor").sum()), (pro, det)
    assert sum(r[c["p1"]] >= 4 for r in f) == (t("SAT") == "Satisfecho").sum()
    assert sum(r[c["p2"]] >= 4 for r in f) == t("ESF").isin(["Muy fácil", "Fácil"]).sum()
    assert sum(r[c["p6"]] >= 4 for r in f) == t("ESF_PAGO").isin(["Muy fácil", "Fácil"]).sum()
    assert sum(r[c["p9"]] is not None for r in f) == df["SAT_COBRO"].notna().sum()
    print(f"NPS {(pro - det) / n * 100:.1f} · SAT {sum(r[c['p1']] >= 4 for r in f) / n * 100:.1f}% · "
          f"CES {sum(r[c['p2']] >= 4 for r in f) / n * 100:.1f}%")
    assert not re.search(r"\d{5,}", texto), "quedó una secuencia de 5+ dígitos"
    assert "Insatsifecho" not in texto and "\r" not in texto
    print(f"OK · {n} encuestas · {len(d['dic'])} categorías · {len(texto)/1024:.0f} KB -> {SALIDA}")
