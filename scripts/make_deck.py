#!/usr/bin/env python3
"""Generate docs/presentation.html: 10 slides, self-contained, keyboard driven.

Images are embedded as base64 so the file can be copied to a USB stick or
opened on a classroom machine with no repository around it. Kept out of the
build path on purpose: it is a one-off generator, not part of the pipeline.
"""
import base64
import html
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMG = REPO / "docs" / "images"
OUT = REPO / "docs" / "presentation.html"


def img(name: str) -> str:
    data = base64.b64encode((IMG / name).read_bytes()).decode()
    return f"data:image/png;base64,{data}"


SLIDES = []


def slide(title: str, body: str, cls: str = "", note: str = "") -> None:
    SLIDES.append((title, body, cls, note))


slide("Seguridad y DevSecOps sobre una red 5G propia", """
  <p class="lead">Un laboratorio 5G Standalone, una aplicación protegida encima
  y una cadena de CI/CD que la prueba y decide <em>con evidencia</em>.</p>
  <p class="meta">Proyecto 2 · Telecommunication Security, DevSecOps and Traffic Intelligence<br>
  Javier Verdú Gambín · DE0849 · 2026</p>
""", cls="cover")

slide("El sistema, en una frase y un dibujo", """
  <div class="flow">
    <span>UE</span><i>→</i><span>gNB</span><i>→</i><span>UPF</span><i>→</i>
    <span class="hi">N6</span><i>→</i><span>Nginx<br><small>TLS</small></span><i>→</i>
    <span class="hi">Django</span>
  </div>
  <ul class="tight">
    <li>El <b>plano de usuario 5G</b> es real: sesión PDU, <code>uesimtun0</code>, ruta 10.20.6.0/24.</li>
    <li>La aplicación vive en <code>app-net</code>, aislada; Nginx es la frontera TLS.</li>
    <li>Scenario B añade un laboratorio de pruebas de seguridad alrededor, no una segunda red.</li>
  </ul>
""")

slide("Escenario A: los controles se demuestran, no se describen", """
  <div class="cols">
    <ul class="tight">
      <li>TLS 1.2 y 1.3 con <code>--cacert</code>, no <code>-k</code></li>
      <li>301 → 200 y cabeceras HSTS, X-Frame-Options, nosniff</li>
      <li>login, permisos, CSRF (200 con token, 403 sin él)</li>
      <li>cookies <code>Secure</code> + <code>HttpOnly</code> + <code>SameSite=Lax</code></li>
      <li>el gateway ve la IP real del UE: no hay NAT</li>
    </ul>
    <figure><img src="__VERIFY__" alt="verify-phase1.sh"><figcaption>1E: 38 comprobaciones, 0 fallos</figcaption></figure>
  </div>
""")

slide("Escenario B: la cadena, y un solo rojo explicable", """
  <div class="stages">
    <span>1E</span><span>2A</span><span>2B</span><span>2C</span><span class="new">2C-Advanced</span><span>2D</span><span>2E gate</span>
  </div>
  <div class="cols">
    <ul class="tight">
      <li>172 comprobaciones, 0 fallos</li>
      <li>cada fase escribe su evidencia con el mismo <code>RUN_ID</code></li>
      <li>build 20: <b class="ok">PASS</b> · build 21: <b class="bad">FAIL</b> solo en el gate</li>
    </ul>
    <figure><img src="__HISTORY__" alt="historial de builds"><figcaption>mismo pipeline, dos políticas</figcaption></figure>
  </div>
""")

slide("Los controles positivos: probar que el detector detecta", """
  <div class="cards">
    <div class="card"><div class="num">40018</div><p>ZAP detecta el SQLi controlado en
    <code>/rest/user/login</code> y el payload queda en <code>instances[]</code>: <code>attack='</code>, <code>evidence=HTTP 500</code>.</p></div>
    <div class="card"><div class="num">44</div><p>Suricata dispara SID 1000001 sobre el PCAP del run
    (20 eventos en la muestra); el JSON guarda <code>alerts_by_signature</code>.</p></div>
  </div>
  <p class="note">Si el control no dispara, el build no decide: correlación 22/22 exige ambos.</p>
""")

slide("El gate: la misma evidencia, dos políticas", """
  <table class="t">
    <tr><th>Condición</th><th>Clase</th><th>Efecto</th></tr>
    <tr><td>correlación 22/22, ZAP 40018, SID 1000001, Trivy informó</td><td>requerida</td><td>sin ellas no hay decisión</td></tr>
    <tr><td>HIGH/CRITICAL &gt; umbral (0)</td><td>bloqueante solo en ENFORCE</td><td>20 PASS con 70 · 21 FAIL</td></tr>
    <tr><td>analytics 98/135 marcadas</td><td>informativa</td><td><code>gate_impact: none</code></td></tr>
    <tr><td>Trivy de nuestras imágenes (51, 126)</td><td>informativa</td><td>se declaran, no bloquean</td></tr>
  </table>
""")

slide("Evaluación independiente: ISCXIDS2012", """
  <table class="t small">
    <tr><th>Día</th><th>Escenario</th><th>Flujos</th><th>Ataques</th></tr>
    <tr><td>12/6</td><td>SSH brute force</td><td>133.193</td><td>2.086</td></tr>
    <tr><td>13/6</td><td>infiltración</td><td>275.528</td><td>20.358</td></tr>
    <tr><td>14/6</td><td>HTTP DoS</td><td>171.380</td><td>3.776</td></tr>
    <tr><td>15/6</td><td>DDoS botnet IRC</td><td>571.698</td><td>37.460</td></tr>
    <tr><td>16/6</td><td>normal</td><td>522.263</td><td>11</td></tr>
  </table>
  <p class="note">1,67 M de flujos leídos y contados; coinciden al flujo con la tabla publicada.
  Subset: 603.691 flujos (todos los ataques + muestra de normales).</p>
""")

slide("Resultados: qué ve el modelo y qué no", """
  <table class="t small">
    <tr><th>Escenario</th><th>Recall</th><th>FPR</th><th>No supervisado</th></tr>
    <tr><td>DDoS IRC</td><td class="ok">0.998</td><td>6,07 %</td><td>0.000</td></tr>
    <tr><td>infiltración</td><td>0.949</td><td>1,18 %</td><td>0.018</td></tr>
    <tr><td>HTTP DoS</td><td>0.842</td><td>2,00 %</td><td>0.020</td></tr>
    <tr><td>SSH (no visto)</td><td class="bad">0.301</td><td>2,15 %</td><td>0.000</td></tr>
    <tr><td><b>global</b></td><td><b>0.951</b> · P 0.793</td><td>2,92 %</td><td><b>0.007</b></td></tr>
  </table>
  <p class="note">El 96,9 % de accuracy engaña: solo el 3,80 % es ataque. Un IDS detecta
  las familias que ha aprendido; el no supervisado, con rasgos marginales, casi nada.</p>
""")

slide("Firmas sobre paquetes: 25.771 alertas, 0 del ataque", """
  <div class="cards">
    <div class="card"><div class="num">9,65 M</div><p>paquetes del 14/6 por Suricata 8.0.8
    con ET Open (69.570 reglas, 53.593 activas).</p></div>
    <div class="card"><div class="num">0</div><p>alertas de DoS en la ventana del flood
    (20:30–21:35 UTC, 641 alertas en total).</p></div>
    <div class="card"><div class="num">0/10</div><p>fuentes etiquetadas como ataque recibieron
    una alerta con firma de DoS.</p></div>
  </div>
  <p class="note">Las firmas miran payloads; el flood usa peticiones HTTP corrientes.
  Ahí es donde el modelo de flujo (0.842) aporta, y por eso es <em>complementario</em> y no el gate.</p>
""")

slide("Lo que no demuestra, y por qué se puede defender", """
  <div class="cols">
    <ul class="tight bad-list">
      <li>Que Juice Shop sea seguro: es vulnerable a propósito.</li>
      <li>Que no haya otros ataques: una regla local.</li>
      <li>Nada del plano 5G en Scenario B.</li>
      <li>Que los 70 CVEs sean explotables aquí.</li>
      <li>Un benchmark de 2010 no es una red 5G real.</li>
    </ul>
    <div class="closing">
      <p>Dos tareas LLM, documentadas con su discrepancia:</p>
      <p class="kv"><b>70/70</b> hallazgos HIGH/CRITICAL con componente exacto en el SBOM<br>
      <b>37/37</b> URIs alertadas por Suricata cubiertas por analytics (+8 extra)</p>
      <p class="end">Un IDS solo detecta lo que ha aprendido;<br>un gate solo decide si la evidencia está completa.</p>
    </div>
  </div>
""")

SLIDES[2] = (SLIDES[2][0], SLIDES[2][1].replace("__VERIFY__", img("verify-1e.png")), SLIDES[2][2], SLIDES[2][3])
SLIDES[3] = (SLIDES[3][0], SLIDES[3][1].replace("__HISTORY__", img("build-history.png")), SLIDES[3][2], SLIDES[3][3])

CSS = """
:root{--bg:#0d1117;--panel:#161b22;--ink:#e6edf3;--dim:#8b949e;--acc:#2dd4bf;--warn:#f59e0b;--bad:#f87171;--ok:#4ade80}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.deck{height:100%;display:flex;align-items:center;justify-content:center}
.slide{display:none;width:min(96vw,1600px);height:min(92vh,900px);padding:5vh 6vw;
  flex-direction:column;justify-content:center;position:relative}
.slide.on{display:flex}
h1{font-size:clamp(28px,4.2vw,64px);line-height:1.1;margin:0 0 2.2vh;
  letter-spacing:-.02em;border-left:8px solid var(--acc);padding-left:1.2vw}
h1 small{display:block;font-size:.42em;color:var(--dim);font-weight:500;margin-top:1.4vh;border:0}
.lead{font-size:clamp(20px,2.6vw,40px);line-height:1.35;margin:2vh 0 4vh;max-width:48ch}
.meta{font-size:clamp(14px,1.3vw,22px);color:var(--dim);line-height:1.7}
ul{font-size:clamp(16px,1.75vw,28px);line-height:1.5;margin:0;padding-left:1.2em}
ul.tight li{margin:.9vh 0}
code{background:#21262d;border-radius:6px;padding:.1em .35em;font-size:.9em}
.flow{display:flex;flex-wrap:wrap;align-items:center;gap:.6vw;font-size:clamp(15px,1.6vw,26px);
  margin:1vh 0 3vh;color:var(--dim)}
.flow span{background:var(--panel);border:1px solid #30363d;border-radius:10px;padding:.7em 1em;text-align:center}
.flow span.hi{border-color:var(--acc);color:var(--acc)}
.flow i{font-style:normal;color:#30363d}
.stages{display:flex;gap:.6vw;flex-wrap:wrap;margin:1vh 0 3vh}
.stages span{background:var(--panel);border:1px solid #30363d;border-radius:8px;padding:.6em 1em;
  font-size:clamp(13px,1.4vw,22px)}
.stages span.new{border-color:var(--acc);color:var(--acc)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:2.6vw;align-items:center}
figure{margin:0}
figure img{width:auto;max-width:100%;max-height:58vh;object-fit:contain;border-radius:10px;border:1px solid #30363d;background:#fff;display:block;margin:0 auto}
figcaption{color:var(--dim);font-size:clamp(11px,1vw,16px);margin-top:1vh;text-align:center}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:2vw;margin:2vh 0 3vh}
.card{background:var(--panel);border:1px solid #30363d;border-radius:14px;padding:2vh 1.4vw}
.card .num{font-size:clamp(34px,4vw,64px);font-weight:700;color:var(--acc);line-height:1}
.card p{color:var(--ink);font-size:clamp(13px,1.25vw,20px);line-height:1.45;margin:1.2vh 0 0}
table.t{width:100%;border-collapse:collapse;font-size:clamp(13px,1.4vw,24px)}
table.t th{text-align:left;color:var(--dim);font-weight:600;border-bottom:2px solid #30363d;padding:.7vh .6vw}
table.t td{border-bottom:1px solid #21262d;padding:.7vh .6vw}
table.small{font-size:clamp(12px,1.15vw,20px)}
.note{color:var(--dim);font-size:clamp(12px,1.15vw,20px);line-height:1.5;margin-top:3vh;max-width:70ch}
.ok{color:var(--ok)}.bad{color:var(--bad)}
.bad-list li{color:#fca5a5}
.closing{background:var(--panel);border:1px solid #30363d;border-radius:14px;padding:3vh 2vw}
.closing p{font-size:clamp(13px,1.25vw,20px);line-height:1.5;margin:0 0 1.6vh}
.kv{color:var(--acc)}
.end{font-size:clamp(16px,1.7vw,26px)!important;color:var(--ink);margin-top:3vh!important;line-height:1.35}
.bar{position:fixed;left:0;bottom:0;height:4px;background:var(--acc);transition:width .2s}
.nav{position:fixed;right:18px;bottom:14px;color:var(--dim);font-size:13px;letter-spacing:.06em}
@media print{
  html,body{background:#fff;color:#111}
  .slide{display:flex!important;page-break-after:always;width:100%;height:100vh;padding:6vh 6vw}
  .bar,.nav{display:none}
  :root{--panel:#f3f4f6;--dim:#4b5563;--ink:#111}
  .card,.closing{border-color:#d1d5db}
  code{background:#e5e7eb}
}
"""


def build() -> str:
    parts = [
        "<!doctype html><html lang='es'><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Proyecto 2 — Seguridad y DevSecOps sobre 5G</title>",
        f"<style>{CSS}</style><body><div class='deck'>",
    ]
    for i, (title, body, cls, note) in enumerate(SLIDES, start=1):
        classes = "slide on" if i == 1 else "slide"
        if cls:
            classes += " " + cls
        parts.append(f"<section class='{classes}' id='s{i}'>")
        parts.append(f"<h1>{html.escape(title)}</h1>")
        parts.append(body)
        parts.append("</section>")
    parts.append("</div><div class='bar' id='bar'></div>")
    parts.append("<div class='nav' id='nav'>1 / 10 · ← →</div>")
    parts.append("""
<script>
const slides=[...document.querySelectorAll('.slide')];
let i=0;
function show(n){
  i=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((s,k)=>s.classList.toggle('on',k===i));
  document.getElementById('bar').style.width=((i+1)/slides.length*100)+'%';
  document.getElementById('nav').textContent=(i+1)+' / '+slides.length+' · ← →';
  location.hash='s'+(i+1);
}
addEventListener('keydown',e=>{
  if(['ArrowRight','ArrowDown','PageDown',' '].includes(e.key)){e.preventDefault();show(i+1);}
  if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){e.preventDefault();show(i-1);}
  if(e.key==='Home')show(0); if(e.key==='End')show(slides.length-1);
  if(e.key==='f'){document.documentElement.requestFullscreen&&document.documentElement.requestFullscreen();}
});
addEventListener('click',e=>{show(e.clientX>innerWidth*0.5?i+1:i-1);});
const start=parseInt((location.hash||'').replace('#s',''),10);
show(Number.isFinite(start)&&start>0?start-1:0);
</script></body></html>""")
    return "".join(parts)


if __name__ == "__main__":
    OUT.write_text(build())
    print(f"{OUT} {OUT.stat().st_size / 1e6:.2f} MB, {len(SLIDES)} slides")
