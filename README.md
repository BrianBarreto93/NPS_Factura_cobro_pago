# Tablero NPS · SAT · CES — Facturación, cobros y pago (Hogar y Móvil)

Tablero de seguimiento de las encuestas **419 · Factura, pago y cobro (Hogar)** y **508 · Factura, pago y cobro Móvil**. Es una página HTML estática (`tablero/index.html`) que lee `tablero/datos.json`. Ese JSON lo genera `construir_datos.py` desde Oracle, tabla `INVITADO_15.TBL_ENC_FACT_PAGOS_COBROS`.

## Actualización mensual

1. Verifica que el mes nuevo ya esté cargado en `TBL_ENC_FACT_PAGOS_COBROS` (columna `ANIO_MES_CORTE`, una carga por `TIPO_BASE`).
2. Regenera los datos:
   ```bash
   /opt/apps/claro_agente_ai/.venv/bin/python construir_datos.py
   python3 exportar_html.py   # .html autocontenido en Outputs/ para compartir
   ```
   El script muestra cuántas encuestas tomó de Hogar y de Móvil y el NPS, SAT y CES del total. Si falla un chequeo, no publiques el tablero hasta revisar la causa.
3. Abre el tablero servido por HTTP (por `file://` no carga los datos):
   ```bash
   python3 -m http.server 8891 --bind 127.0.0.1 --directory tablero
   ```
   Entra a http://127.0.0.1:8891/ y apaga el servidor al terminar (`pkill -f "http.server 8891"`).

### Fuente

- Credenciales en `.env` de esta carpeta (`ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DBNAME`; las mismas de CSAT Hogar). No se versiona.
- La consulta corre en una transacción de solo lectura y pide solo las columnas que usa el tablero.
- `TIPO_BASE` (HOGAR / MOVIL) alimenta el filtro **Negocio**: General (las dos), Hogar o Móvil.
- El mes sale de `MES_ENCUESTA` y el año de `FECHA_HORA_GESTION`. Una encuesta de diciembre gestionada en enero queda en diciembre del año anterior.
- El último mes cargado se marca como "corte al DD de mes", con la última fecha de gestión del negocio elegido (en agosto 2026: Hogar al 28, Móvil al 25).
- El parquet y los Excel `BDD Fact Hogar_*.xlsx` ya no se leen; quedan como respaldo histórico.

### Qué valida el script

- Todos los nombres de `MES_ENCUESTA` se reconocen.
- No hay `REGISTRO_ID` repetidos dentro de un mismo negocio.
- Lo calculado cuadra con las columnas ya clasificadas de la tabla: promotores y detractores contra `NPS`, satisfechos contra `SAT`, fácil contra `ESF` y `ESF_PAGO`, y respuestas de cobro contra `SAT_COBRO`.
- En `datos.json` no queda ninguna cifra de 5 o más dígitos (cédulas, cuentas, teléfonos).

## Indicadores

| Indicador | Pregunta | Cálculo |
|---|---|---|
| NPS | ¿Qué tan dispuesto estaría en recomendarnos? (0–10) | % promotores (9–10) − % detractores (0–6) |
| SAT factura | P1 · satisfacción con la facturación (1–5) | % que califica 4 o 5 |
| CES factura | P2 · facilidad para entender la factura (1–5) | % que califica 4 o 5 |
| SAT pago | P5 · satisfacción con el proceso de pago | % 4 o 5 |
| CES pago | P6 · facilidad para pagar | % 4 o 5 |
| SAT cobro | P9 · satisfacción con el cobro (solo quien recibió recordatorio, P8 = Sí) | % 4 o 5 |

- Las diferencias entre periodos o grupos se muestran en **pp** (puntos porcentuales).
- Los cortes con menos de 30 encuestas salen en gris o no se grafican.
- **Impacto en NPS** (vista Recorrido): techo de puntos que podría ganar el NPS general = brecha (NPS de quien responde favorable en un paso menos NPS de quien no) × % de encuestas con respuesta desfavorable en ese paso. Es un máximo teórico, no una proyección; no se suman entre pasos.
- **Fricción**: un paso del recorrido con respuesta desfavorable.

## Vistas

1. **Resumen.** KPI con variación frente al mes anterior, evolución mensual, composición del NPS y lectura automática del periodo.
2. **Tendencias y segmentos.** Región por mes, Facturación frente a Cobranza, canal de pago y ciudad o zona.
3. **Recorrido y drivers.** Los pasos de factura → pago → cobro, la matriz de drivers y el NPS según el número de fricciones.
4. **Constelación de motivos.** NPS, SAT o CES por motivos o por emociones. Arranca con los elementos más grandes; un clic abre la rama y el centro la cierra.
5. **Emociones y comentarios.** Emociones por parte del proceso, motivos de detractores o neutros, y comentarios con buscador.

Todos los filtros (negocio, mes, región, tipo de estudio, canal de pago, ciudad o zona, segmento NPS) afectan las 5 vistas, y un clic en una gráfica también filtra.

## Datos personales

`datos.json` no lleva nombre, teléfono, cuenta, identificación ni correo: esas columnas ni siquiera se piden a Oracle. Tampoco se usa `OBSERVACION`, que trae el nombre de quien contesta. A los comentarios se les reemplazan las cifras de 5 o más dígitos por `[#]`. El parquet, los Excel y `.env` no se copian a `tablero/` ni se publican.

## Notas de la fuente

- `CIUDAD` mezcla ciudades y zonas operativas (p. ej. "Medellín Norte", "Antioquia 1"). El tablero las muestra tal cual, salvo las variantes de Bogotá y algunos nombres con mal encoding, que se corrigen en `construir_datos.py` (`CIUDADES`).
- Cobranza (Hogar y Móvil) y 1.671 encuestas de Facturación Móvil no traen canal de pago y aparecen como "Sin dato".
- Móvil trae el canal en `DES_CANAL` o en `DES_MEDIO` según la fila (p. ej. BANCO/NEQUI y NEQUI/BANCO); se toma el genérico de los dos (`CANALES` en `construir_datos.py`). Hogar usa `DES_CANAL` tal cual.
- Hogar usa cinco regiones (Centro, Costa, Noroccidente, Occidente, Oriente) y Móvil tres (Costa, Occidente, Oriente; Bogotá cae en Oriente y Medellín en Occidente). En General, "Oriente" y "Occidente" mezclan las dos divisiones.
- En Móvil, `P11_2_OTRO` es casi siempre una subcategoría corta ("No brinda información", "Voz y Datos") y no un comentario libre; aparece así en Comentarios.
- Las categorías se unifican sin distinguir mayúsculas ni espacios, y los saltos de línea (`_x000D_` que dejó la carga desde Excel) se limpian.

## Lámina de dolores del cliente

`analisis_dolores.py MOVIL` (o `HOGAR`) calcula las cifras de la lámina "Dolores del cliente" desde la misma tabla de Oracle; la de Móvil está en `Outputs/Dolores del cliente · Factura, pago y cobro Móvil (NPS).html` y sus cifras en `Outputs/dolores_movil.json`.

- El script original de la lámina de Hogar no estaba en el repo; las reglas se reconstruyeron calibrando contra ella. Con `HOGAR` el script imprime la comparación: E2, E3 y E5 (y sus detalles) dan exacto; E1, E4 y E6 usan texto libre y se alejan entre 1 % y 3 %; "no reciben la factura" queda en 346 frente a 415.
- E1 = P4 No o no recibe la factura · E2 = P2 ≤ 2 o valores no claros · E3 = P3 No · E4 = incrementos o cargos no reconocidos (motivos + texto) · E5 = P5 ≤ 2 o P6 ≤ 2 · E6 = P9 ≤ 2 o motivo de cobranza en P1.2.
