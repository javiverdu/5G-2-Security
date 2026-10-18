# Scenario B — Observability (page 6)

The deployment already ships an observability stack, so page 6 is about *seeing*
the 5G path work, not building it:

| Component | Container | Host port | Purpose |
|---|---|---|---|
| Prometheus | `metrics` | `9090` | scrapes the Open5GS NFs on `:9091` |
| Grafana | `grafana` | `3000` | dashboards (`open5gs` / `open5gs`) |

The Open5GS NFs (AMF, SMF, PCF, UPF, …) expose Prometheus metrics on `:9091`;
Prometheus scrapes them every 5 s and Grafana visualises them with the provisioned
`Open5GS` dashboard.

## 1. Check it

```bash
cd scenario-b
./scripts/metrics-check.sh
```

It prints the container status, the Prometheus **target health**, a sample of the
Open5GS metric names and the Grafana status. Expected targets:

| Job | Health | Note |
|---|---|---|
| `amf`, `smf`, `pcf`, `upf` | **up** | the SA core we deploy |
| `mme`, `pcrf`, `hss` | down / removed | **4G EPC** functions with a 5G replacement: MME→AMF, PCRF→PCF, HSS→UDM/UDR. Not part of 5G SA, so no container listens on them |

The upstream `prometheus.yml` is generic (it covers 4G and 5G deployments), so the
4G jobs show as `DOWN` even though nothing is wrong. **They are left as-is** on
purpose: `mme`, `pcrf` and `hss` are simply **not used** in 5G SA, so their `DOWN`
state in *Status → Targets* is expected and harmless. Ignore those three targets;
the ones that matter are `amf`, `smf`, `pcf`, `upf`.

## 2. Open the UIs (from the VM or its management IP)

* Prometheus — <http://127.0.0.1:9090> → *Status → Targets* (the SA jobs `UP`).
* Grafana — <http://127.0.0.1:3000> (login `open5gs` / `open5gs`).

**Where the dashboard is:** this repository ships its own Grafana provisioning
(`scenario-b/grafana/`), so the dashboard appears in the folder **`Services`**
with the title **`Open5GS`**. In Grafana open *Dashboards* (or hit `g` then `d`)
and look under `Services`, or type `Open5GS` in the search box. It is **not** on
the Grafana home page by default.

> Note the two spellings: the **datasource** is named `Open5Gs` (the upstream
> name) and the **dashboard** is titled `Open5GS`. Both are correct; do not
> "fix" one to match the other.

Check it from the CLI:

```bash
curl -s -u open5gs:open5gs 'http://127.0.0.1:3000/api/search?type=dash-db' | python3 -m json.tool
curl -s -u open5gs:open5gs 'http://127.0.0.1:3000/api/datasources'   | python3 -m json.tool
```

### Why provisioning fails from a VirtualBox shared folder

If the repository lives on a **VirtualBox shared folder** (`/media/sf_*`), the
bind mount into `/etc/grafana/provisioning` is **not readable by Grafana's user
(472)**, so nothing is provisioned:

```
logger=provisioning.dashboard  error="open /etc/grafana/provisioning/dashboards: permission denied"
logger=provisioning.datasources error="open /etc/grafana/provisioning/datasources: permission denied"
```

vboxsf does not give the Unix permissions Grafana needs. Two ways out: run the
repository from a **native path** (not a shared folder), or **import via the API**
(recommended, works regardless).

### Import the datasource + dashboard via API

```bash
cd scenario-b
./scripts/grafana-import.sh
```

It creates the Prometheus datasource (fixed UID `PA240B69645956401`) and imports
the `Open5GS` dashboard into Grafana's own database (the `grafana_data` volume),
so it survives restarts and does not depend on the shared folder. Then open
<http://127.0.0.1:3000/dashboards> → folder **General** → **Open5GS**.

### Manual import (UI)

1. *Dashboards → New → Import*.
2. *Upload JSON file* → pick
   `scenario-b/grafana/dashboards/open5gs_dashboard.json` (or paste its contents
   into the JSON box).
3. *Load*; if asked for a datasource, choose **Open5Gs** → *Import*.
   If there is no datasource yet, create one first in *Connections → Data
   sources*: Prometheus, URL `http://172.22.0.36:9090`; set its **UID** to
   `PA240B69645956401` so the panels resolve (or pick it in the import dialog,
   which remaps them).

> The `grafana-fix.sh` helper installs the provisioning files for the case where
> the repository is on a native path; on a shared folder it cannot help because of
> the permission issue above — use `grafana-import.sh` there.

## 3. Correlate with the traffic tests

Run a test in another terminal and watch the counters move:

```bash
# generate user traffic
docker exec nr_ue ping -c 20 10.20.6.20
docker run --rm --network container:nr_ue networkstatic/iperf3:latest -c 10.20.6.21 -t 10
```

Then look for the UPF/AMF/SMF metrics (in Prometheus or Grafana). Useful queries:

| Query (Prometheus) | Shows |
|---|---|
| `up{job=~"amf|smf|pcf|upf"}` | scrape health per NF |
| metrics containing `fivegs` / `session` | Open5GS counters (see `metrics-check.sh` output) |
| `rate(...[1m])` on the GTP-U packet counter | N3 user-plane packets/s while iperf3 runs |

> Metric names are Open5GS-version specific; `metrics-check.sh` lists the actual
> names exposed by your build rather than hard-coding them.

## 4. What to capture for the report

1. Prometheus *Status → Targets* showing the SA jobs `UP`.
2. Grafana Open5GS dashboard **before** traffic (baseline) and **during** an
   iperf3 transfer — the change is the evidence that the metrics track the path.
3. (Optional) a graph of the GTP-U / session metric over the test window.

## 5. Notes / limitations

* `mme`, `pcrf`, `hss` targets are 4G-only; in Scenario B they stay down or are
  simply unused. That is expected, not a fault.
* The observability stack is **passive**: it does not affect the data path. The
  packet-level evidence of page 4 and the measurements of page 5 remain the
  primary proof; Grafana adds a live, system-level view.
* RAM: Prometheus + Grafana add a few hundred MB; the VM should have ≥ 8 GB.

## 6. Field note — running from a VirtualBox shared folder (anecdote)

**Environment.** The lab is a single Ubuntu VM, and the repository is opened from
a VirtualBox **shared folder** at `/media/sf_5G_project/5G-project-RTU` (the same
tree is visible on the host). This is convenient for editing, but it broke
Grafana's file provisioning.

**Symptom.** Grafana's home showed no dashboard and no `Services` folder, and
`grafana-fix.sh` reported:

```
logger=provisioning.dashboard   error="open /etc/grafana/provisioning/dashboards: permission denied"
logger=provisioning.datasources error="open /etc/grafana/provisioning/datasources: permission denied"
```

**Cause.** Grafana runs as the unprivileged `grafana` user (uid 472) and the
`./grafana/` directory is bind-mounted at `/etc/grafana/provisioning`. vboxsf does
not expose Unix permissions the way Grafana needs, so uid 472 cannot read the
files and **nothing is provisioned** — not the datasource, not the dashboard. It
was never a bad dashboard: the files were never read.

**Workaround used (works from the shared folder).** Import over the Grafana API
instead of the filesystem:

```bash
cd scenario-b
./scripts/grafana-import.sh
```

`grafana-import.sh` creates the Prometheus datasource (fixed UID
`PA240B69645956401`) and imports `open5gs_dashboard.json` into Grafana's database
(the `grafana_data` volume). Because it does not touch `/etc/grafana`, it is
immune to the vboxsf permissions and survives `docker restart grafana`. After it
runs, the dashboard appears under **Dashboards → General → Open5GS**.

**Alternative.** If the repository is cloned to a **native path** (e.g.
`~/5G-project-RTU` on the VM), the bind mount keeps normal permissions and the
file provisioning works; `grafana-fix.sh` (or `fetch-upstream.sh`) is then enough
and the API import is unnecessary.

**Takeaway for the report.** The failure was environmental (shared-folder
permissions vs. a non-root container user), diagnosed from the container log;
the fix is architectural (store the dashboard in Grafana's own DB) rather than a
manual click-through. The manual UI steps above remain as a fallback.
