"""Dolores del cliente · Factura, pago y cobro: cifras de las láminas de dolores (Hogar y Móvil).

Uso: /opt/apps/claro_agente_ai/.venv/bin/python analisis_dolores.py MOVIL > Outputs/dolores_movil.json
     (o HOGAR; con HOGAR además compara contra la lámina de Hogar entregada antes)

Las mismas reglas para los dos negocios. Un cliente puede tener varios dolores.
"""
import json
import re
import sys
import unicodedata
import warnings

import pandas as pd

from construir_datos import consultar

warnings.filterwarnings("ignore", message="This pattern is interpreted as a regular expression")

NPS, P1, P2, P3, P4, P5, P6, P9 = ("P11_RECOMENDACION_NPS", "P1_SATISFACCION_FACTURA", "P2_FACILIDAD_ENTENDER",
                                   "P3_VALORES_ACORDES_PLAN", "P4_TIEMPO_SUFICIENTE_REVISAR", "P5_SATISFACCION_PAGO",
                                   "P6_FACILIDAD_PAGO", "P9_SATISFACCION_COBRO")
MOT = ["P1_2_MOTIVO_CALIF", "P2_1_DETALLE_DIFICIL", "P3_1_CONCEPTOS_ERRONEOS", "P5_1_MOTIVO_CALIF",
       "P6_1_DETALLE_DIFICIL", "P9_1_MOTIVO_CALIF"]
TXT = ["P2_2_DETALLE_DIFICIL", "P3_2_PROFUNDIZACION", "P5_2_MOTIVO_CALIF", "P6_2_DETALLE_DIFICIL", "P9_1_OTRO",
       "P10_1_OTRO", "P11_2_OTRO", "P7_1_OTRO_CUAL", "P7_2_1_MOTIVO_FALTA_CLARIDAD", "P10_3_OTRO", "P7_3_OTRO_CUAL",
       "P7_4_OTRO"]
# Texto libre (normalizado: minúsculas, sin tildes). Son las únicas reglas aproximadas: el resto sale de
# calificaciones y motivos cerrados.
RX_NO_LLEGA = (r"(no|ni|nunca) (le |me )?(ha |han |volvio a )?(llega|llego|llegan|llegaba|llegado|lega|llegar|envian|enviaban|"
               r"enviado|mandan|recib)[^|]{0,30}factur|factur[^|]{0,30}(no|ni|nunca) (le |me )?(llega|llego|ha llegado|recib)|"
               r"no (le |me )?(llega|llego|lega)\b|le (llegara|legara) la factura|sin (recibir|la) factura|por ningun medio|"
               r"(no|dificil)[^|]{0,15}descargar la factura|factura[^|]{0,20}(llega|llegaba) cuando")
RX_INCREMENTO = (r"increment|aument|subi(o|eron|da|endo)|se (le )?(ha )?sub|alza|reajust|cambio de plan|"
                 r"cambiaron (el |de )?plan|valor(es)? (mas )?(alto|elevado)s?|(llega|llego|llegaba)[^|]{0,20}(mas )?(alta|cara)")
RX_CARGO = (r"doble factur|no (lo |los |la )?(he |ha |habia )?(solicit|ped|autoriz)|sin (su |mi )?(consentimiento|autoriz)|"
            r"(despues de|ya) (haber )?(cancel|retir)|servicio[^|]{0,15}(cancelado|suspendid|retirado)|"
            r"cobr[^|]{0,40}(suspend|cancelad|no (usa|utiliza|tiene))|adicional|no reconoc|reconexion|"
            r"(hbo|netflix|paramount|revista|deco|seguro)[^|]{0,30}(cobr|gratis|factur)|"
            r"cobr(an|aron|ado|o)[^|]{0,30}(de mas|instalacion|visita|por adelantado|mes completo|productos|cosas|mal\b)|"
            r"sigu(e|en|ieron) (facturando|cobrando)|no (se lo|lo|me lo|le) (cancelaron|retiraron|quitaron)")
COBRANZA = {"llamadas o mensajes excesivos", "gestion de cobranza inadecuada", "acuerdo de pago no cumplido o no respetado"}
# lámina de Hogar entregada (n, % y conteos) para ver qué tanto se aleja la reconstrucción
REF_HOGAR = {"E1": 997, "E1_sin_tiempo": 891, "E1_no_llega": 415, "E2": 599, "E2_dificil": 503, "E2_valores": 309,
             "E3": 1478, "E3_distinto": 799, "E4": 734, "E4_incremento": 424, "E4_cargos": 359, "E5": 455,
             "E5_app": 72, "E5_espera": 70, "E5_referencia": 25, "E5_debito": 18, "E6": 665, "E6_llamadas": 426}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def nps(g):
    return round(100 * ((g[NPS] >= 9).mean() - (g[NPS] <= 6).mean()), 1) if len(g) else None


def marcar(d):
    """Columna booleana por dolor (E1..E6) y por cada métrica de detalle de las tarjetas."""
    mot = d[MOT].apply(lambda r: " || ".join(norm(x) for x in r if pd.notna(x)), axis=1)
    txt = d[TXT].apply(lambda r: " || ".join(norm(x) for x in r if pd.notna(x)), axis=1)
    m = lambda rx, cols=MOT: d[cols].apply(lambda c: c.map(lambda v: bool(re.search(rx, norm(v))) if pd.notna(v) else False)).any(axis=1)
    pago = ["P5_1_MOTIVO_CALIF", "P6_1_DETALLE_DIFICIL"]
    f = pd.DataFrame(index=d.index)
    f["E1_sin_tiempo"] = d[P4].eq("No")
    f["E1_no_llega"] = mot.str.contains("no entrega de la factura") | txt.str.contains(RX_NO_LLEGA)
    f["E1"] = f.E1_sin_tiempo | f.E1_no_llega
    f["E2_dificil"] = d[P2] <= 2
    f["E2_valores"] = m(r"no son claros|errores en los calculos|confusa|cargos adicionales",
                        ["P1_2_MOTIVO_CALIF", "P2_1_DETALLE_DIFICIL", "P5_1_MOTIVO_CALIF"])
    f["E2"] = f.E2_dificil | f.E2_valores
    f["E3"] = d[P3].eq("No")
    f["E3_distinto"] = mot.str.contains(r"valores (que )?no coinciden|no corresponde a lo contratado|terminos y condiciones de la promocion")
    f["E4_incremento"] = mot.str.contains(r"incremento anual|aumento de factura por cambio de plan") | txt.str.contains(RX_INCREMENTO)
    f["E4_cargos"] = (mot.str.contains(r"doble facturacion|servicios suplementarios|cobros fijo movil|reconexion|servicio cancelado")
                      | txt.str.contains(RX_CARGO))
    f["E4"] = f.E4_incremento | f.E4_cargos
    f["E5"] = (d[P5] <= 2) | (d[P6] <= 2)
    f["E5_app"] = m(r"fallas en la app", pago)
    f["E5_espera"] = m(r"tiempo de espera", pago)
    f["E5_referencia"] = m(r"numero de referencia", pago)
    f["E5_debito"] = m(r"pagos automaticos", pago)
    f["E6"] = (d[P9] <= 2) | d["P1_2_MOTIVO_CALIF"].map(lambda v: norm(v) in COBRANZA if pd.notna(v) else False)
    f["E6_llamadas"] = d["P9_1_MOTIVO_CALIF"].map(lambda v: norm(v) == "llamadas o mensajes excesivos" if pd.notna(v) else False)
    return f, txt


def metricas(d):
    f, txt = marcar(d)
    n, det = len(d), d[NPS] <= 6
    t2b = lambda q: round(100 * (d[q] >= 4).sum() / d[q].notna().sum(), 1)
    out = {"n": n, "nps": nps(d), "prom": round(100 * (d[NPS] >= 9).mean(), 1), "detr": round(100 * det.mean(), 1),
           "por_base": {b: {"n": len(g), "nps": nps(g)} for b, g in d.groupby("BASE_ORIGEN")},
           "con_dolor": round(100 * f[[f"E{i}" for i in range(1, 7)]].any(axis=1).mean(), 1),
           "detr_con_dolor": round(100 * f.loc[det, [f"E{i}" for i in range(1, 7)]].any(axis=1).mean(), 1),
           "detr_valor_no_plan": round(100 * f.E3[det].mean(), 1),
           "t2b": {"factura": t2b(P1), "entender": t2b(P2), "pagar": t2b(P5), "cobro": t2b(P9), "ces_pago": t2b(P6)},
           "llamadas_pct_motivos_cobro": round(100 * f.E6_llamadas.sum() / d["P9_1_MOTIVO_CALIF"].notna().sum(), 1),
           "insat_cobro_por_base": {b: round(100 * (g[P9] <= 2).sum() / g[P9].notna().sum(), 1) for b, g in d.groupby("BASE_ORIGEN")},
           "conteos": {k: int(v) for k, v in f.sum().items()}, "dolores": {}}
    for i in range(1, 7):
        e = f[f"E{i}"]
        con, sin = nps(d[e]), nps(d[~e])
        out["dolores"][f"E{i}"] = {"n": int(e.sum()), "pct": round(100 * e.mean(), 1), "nps_con": con, "nps_sin": sin,
                                   "brecha": round(sin - con, 1), "potencial": round(e.mean() * (sin - con), 1),
                                   # comentarios de detractores para elegir la cita (sin los que traen nombres)
                                   "citas": [t[:240] for t in txt[e & det].drop_duplicates().head(40) if t and "nombre" not in t]}
    return out


if __name__ == "__main__":
    neg = (sys.argv[1:] or ["MOVIL"])[0].upper()
    d = consultar(["TIPO_BASE", "REGISTRO_ID", "FECHA_HORA_GESTION", "BASE_ORIGEN", NPS, P1, P2, P3, P4, P5, P6, P9, *MOT, *TXT])
    r = metricas(d[d.TIPO_BASE == neg])
    if neg == "HOGAR":
        for k, v in REF_HOGAR.items():
            print(f"{k:15} lámina {v:5}  reglas {r['conteos'][k]:5}  {r['conteos'][k] - v:+d}", file=sys.stderr)
    print(json.dumps(r, ensure_ascii=False, indent=1))
