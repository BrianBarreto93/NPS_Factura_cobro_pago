"""Empaqueta tablero/ en un solo .html (datos, banner, fuentes y ECharts embebidos) para abrir con doble clic."""
import base64, datetime, pathlib, urllib.request

T = pathlib.Path(__file__).parent / 'tablero'
ECHARTS = 'https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js'


def b64(nombre):
    return base64.b64encode((T / nombre).read_bytes()).decode()


def reemplazar(html, viejo, nuevo):
    assert viejo in html, f'no se encontró en index.html: {viejo[:60]}'
    return html.replace(viejo, nuevo)


html = (T / 'index.html').read_text(encoding='utf-8')
datos = (T / 'datos.json').read_text(encoding='utf-8').replace('</', '<\\/')
echarts = urllib.request.urlopen(ECHARTS, timeout=60).read().decode().replace('</script', '<\\/script')

html = reemplazar(html, '<link rel="preload" href="fuentes/nunitosans.woff2" as="font" type="font/woff2" crossorigin>\n', '')
html = reemplazar(html, '<link rel="preload" href="fuentes/nunito.woff2" as="font" type="font/woff2" crossorigin>\n', '')
for f in ('nunito', 'nunitosans'):
    html = reemplazar(html, f'url("fuentes/{f}.woff2")', f'url("data:font/woff2;base64,{b64(f"fuentes/{f}.woff2")}")')
html = reemplazar(html, 'src="banner.webp"', f'src="data:image/webp;base64,{b64("banner.webp")}"')
html = reemplazar(html, f'<script src="{ECHARTS}"></script>', f'<script>{echarts}</script>')
html = reemplazar(html, "fetch('datos.json').then(r => r.json())", 'Promise.resolve(DATOS)')
html = reemplazar(html, '</head>', f'<script>const DATOS = {datos};</script>\n</head>')

sal = T.parent / 'Outputs' / f'Tablero NPS Factura cobro y pago {datetime.date.today():%Y-%m-%d}.html'
sal.write_text(html, encoding='utf-8')
print(sal, f'{sal.stat().st_size / 1e6:.1f} MB')
