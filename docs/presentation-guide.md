# Presentation guide

Script for a 12–15 minute presentation with demo, plus the numbers to know cold
and the questions that are actually likely. Structure and notes are in English
like the rest of the repository; the lines meant to be spoken are in Spanish
because the presentation is.

## 1. Running order

| Min | What | How | Evidence on screen |
|---|---|---|---|
| 0–1 | What the project is, in one sentence | "Un laboratorio 5G propio, una aplicación segura encima, y una cadena de CI/CD que la prueba y decide con evidencia." | `docs/architecture.md` diagram |
| 1–3 | Scenario A: the path exists | UE → gNB → UPF → N6 → Nginx TLS → Django; segmentation `dn-net` vs `app-net`; login, CSRF, cookies | terminal: `verify-phase1.sh` tail (screenshot `docs/images/verify-1e.png`) |
| 3–6 | Scenario B pipeline in Jenkins | stages 1E→2A→2B→2C→2C-Advanced→2D→2E; evidence per phase with `RUN_ID` | build history: #20 green, #21 red (`docs/images/build-history.png`) |
| 6–8 | The two positive controls | ZAP 40018 and Suricata SID 1000001: the mechanism is proven, not assumed | `security-event-correlation.md` (22/22) and `gate.md` |
| 8–10 | Policy, not scanner | same build, `REPORT_ONLY` passes with 70 H/C, `ENFORCE` fails at the gate only | `gate.json` of run 20 and 21 |
| 10–12 | Independent evaluation on ISCX | per-scenario table; SSH missed (0.301), DDoS 0.998; 0.7 % for the unsupervised baseline | `docs/ids-benchmark.md` tables |
| 12–14 | Signature IDS on real packets | 25,771 alerts, 0 for the flood, 0/10 attack sources | `results/ids-eval/20261123T174056Z-pcap/summary.md` |
| 14–15 | What it does not prove | the honest slide: one rule, benchmark 2010, no CD, no exploitability | `docs/report.md` §13 |

Two minutes saved: if time is short, drop 1–3 and start at the pipeline.

## 2. Demo that cannot fail

Do **not** run the whole pipeline live (3–4 minutes, and it depends on the 5G
path being up). Show artefacts instead; they are already on disk:

```bash
cd ~/Documentos/VSCODE/5G-2-Security
R=results/scenario-b/phase2e/20261123T163741Z
jq -r '.decision, .checks_total' $R/gate.json                      # PASS 5
jq -r '.chain | {app: .application_observation.detected,
                 sid: .network_evidence.sid_alert_count,
                 trivy: .software_artifacts.trivy_high_or_critical}' \
   $R/security-event-correlation.json                             # true 44 70
jq -r '.scenarios | to_entries[] | "\(.key) \(.value.scenario) R=\(.value.supervised.recall)"' \
   results/ids-eval/20261123T170555Z/eval.json
sed -n '1,12p' results/ids-eval/20261123T174056Z-pcap/summary.md
```

If Jenkins is up and they ask to see it: open the job, build 20 (green) and
build 21 (red at the gate). The build history screenshot is the fallback.

## 3. Numbers to know cold

- 172 checks, 0 failed: 38 in 1E, 112 printed by 2A–2E, 22 inside the
  correlation container.
- Correlation 22/22; wrapper 6 (or 7 if it had to rebuild the image).
- PCAP of the run: 856 packets, one hash shared by 2B and 2C.
- Positive controls: ZAP alert 40018, Suricata SID 1000001 with 44 events
  (20 stored).
- Trivy: 70 HIGH/CRITICAL (12 CRITICAL + 58 HIGH); own images 51 and 126,
  informational.
- Gate: `REPORT_ONLY` PASS with 70 recorded; `ENFORCE` FAIL on the threshold.
- ISCX subset: 5 days, 1.67 M flows read, 603,691 kept, 63,691 attacks.
- Supervised: P 0.793 / R 0.951 / F1 0.865 / FPR 2.92 %. Per scenario: DDoS
  0.998, infiltration 0.949, HTTP DoS 0.842, SSH 0.301, normal day precision
  0.007. Unsupervised: R 0.007.
- Signature IDS on 14 June: 9,648,653 packets, 25,771 alerts, 0 DoS-flavoured
  in the flood window, 0 of 10 labelled attack sources.
- LLM tasks: 70/70 SBOM matches; 37/37 Suricata URIs covered by analytics with
  8 extra.

## 4. Questions, and the answer that survives

**¿Por qué SSH solo 0.301?**
Porque en ese experimento el modelo nunca ve un ataque de credenciales: entrena
con DDoS, DoS e infiltración y se examina de SSH. Es un ataque de bajo volumen
que se parece a una sesión normal. Es el resultado más honesto del benchmark:
un IDS detecta las familias que ha aprendido.

**¿Y si hubieras incluido el 17/6?**
Subiría el recall de SSH, porque ese día también es SSH. Lo dejé fuera a
propósito y está escrito como coste de la selección, no escondido.

**El 96,9 % de accuracy, ¿no es buenísimo?**
No. Solo el 3,80 % del tráfico es ataque. Con 2,92 % de FPR, en un SOC eso son
miles de alertas por minuto, y en el día normal la precisión cae a 0,007. Por
eso el informe habla de precision, recall y FPR.

**¿Por qué el no supervisado no detecta nada?**
Porque compara cada característica por separado y los flujos de ataque se
solapan con los normales en todas ellas; hace falta un modelo multivariante.
Es el argumento empírico para que la analítica de 2C-Advanced sea
`supplementary` y el gate dependa de la regla.

**Una firma con 53.593 reglas no detecta el DoS, ¿no está mal configurada?**
Es el resultado esperado: las firmas detectan payloads y el flood usa
peticiones HTTP corrientes. No la tunéé a propósito: se mide el IDS tal cual.
Y aun así generó 25.771 alertas en tráfico normal.

**¿Por qué el dataset no está en Jenkins?**
Son 3,1 GB con licencia académica y no es evidencia de un run. El gate tiene
que seguir atado a la captura viva; mezclarlos haría que un PASS dependiera de
datos de 2010. Está declarado como desviación (§12.1 del informe).

**¿El LLM decide algo?**
No. Las dos tareas están documentadas con su discrepancia: el LLM predijo
hallazgos del SBOM sin componente y la evidencia dio 70/70 coincidencias; y su
"98 contra 44" comparaba peticiones con eventos. El gate lee `gate.json`, no
texto de un modelo.

**¿Qué cambia exactamente entre REPORT_ONLY y ENFORCE?**
Una sola cosa: si un finding HIGH/CRITICAL por encima del umbral bloquea. El
resto de condiciones (correlación, controles, Trivy informó) son requeridas en
ambos modos: si fallan, no hay decisión de seguridad.

**¿Por qué el tag de la imagen sigue en 1.0 si cambiaste el código?**
Porque el enunciado fija `telecom-lab-correlation:1.0` y pide que el manifiesto
lleve ese tag. Lo que cambia no es el nombre: 2E compara el sha256 de
`correlate.py` dentro de la imagen con el del repo, reconstruye si difieren y
falla si no coinciden. `correlate.json` guarda el hash y el image_id.

**¿Por qué el wrapper de 2E imprime 6 y antes 5?**
Porque ahora hay un check más (que la imagen contiene el `correlate.py`
actual) y el de construcción solo corre si falta o está vieja. El 22 sigue
siendo dentro del contenedor.

**¿Por qué cambia el tamaño del archivo entre runs?**
Es un gzip de 56 miembros: cambian el PCAP, el screenshot y los informes Trivy;
el número de miembros no. Lo que no cambia es lo que se verifica: mismo
`RUN_ID` en todo, un solo hash de PCAP, ambos controles.

**¿Qué NO demuestra esto?**
Que Juice Shop sea seguro (es vulnerable a propósito), que no haya otros
ataques (una regla), nada del plano 5G en Scenario B, ni explotabilidad de los
70 CVEs. Está en §13 del informe, con ocho limitaciones declaradas.

**Si te pido que lo repitas ahora, ¿sale igual?**
Sí para la evaluación ISCX: semilla fija, subset fijado por sha256, 40 s de
proceso. No para el build: cada run genera su `RUN_ID` y su PCAP, y por eso la
evidencia es atribuible al build que la produjo.

## 5. If something breaks during the demo

- Jenkins caído → enseña `results/` y las capturas; el build 20/21 ya está
  documentado con su `gate.json`.
- El camino 5G caído (`UE cannot reach 10.20.6.20`) → `docker restart nr_gnb`
  y `nr_ue`, y explica el orden: el N6 rehace el UPF y el UE debe registrarse
  después. Es una respuesta buena, no un fallo.
- `jq` no instalado en el aula → los mismos datos están en `.md` al lado del
  `.json`.
