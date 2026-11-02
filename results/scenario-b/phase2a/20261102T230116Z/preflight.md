# Scenario B — Phase 2A Preflight

- RUN_ID: `20261102T230116Z`
- Build: `jenkins-scenario-b-security-3`
- Started (UTC): 2026-11-02T23:01:20+00:00
- Finished (UTC): 2026-11-02T23:02:12+00:00
- Decision: **PASS** (0 failed of 35)

| Check | Status | Detail |
|---|---|---|
| evidence directory is run-specific and free of stale artifacts | PASS | /evidence/scenario-b/phase2a/20261102T230116Z (unexpected: none) |
| Jenkins build id present | PASS | jenkins-scenario-b-security-3 |
| evidence directory writable | PASS | /evidence/scenario-b/phase2a/20261102T230116Z |
| required Jenkins plugins installed | PASS | 62 plugins present |
| plugin versions match the Release Manifest | PASS | all pinned versions match |
| Docker reachable from Jenkins | PASS | 29.9.2 |
| security-net exists | PASS | security-net |
| Scenario A dn-net present | PASS | dn-net |
| container DNS resolves juice-shop on security-net | PASS | 10.20.10.20       juice-shop  juice-shop |
| Juice Shop reachable | PASS | HTTP 200 |
| target is the controlled Juice Shop v20.2.0 | PASS | reported version 20.2.0 |
| Selenium Grid reachable and ready | PASS | HTTP 200, ready=True |
| a browser session can be created | PASS | session c40250892ab6b45179e2d89b439d3c7a |
| ZAP image available | PASS | ghcr.io/zaproxy/zaproxy:stable |
| ZAP executable reports a version | PASS | 2.17.0 |
| targeted ZAP plan.yaml present | PASS | /var/jenkins_home/workspace/scenario-b-security/project2/scenario-b/security/zap/plan.yaml |
| plan.yaml is valid YAML with requestor and activeScan jobs | PASS | jobs=['spider', 'requestor', 'activeScan', 'report'] |
| capture image available | PASS | telecom-lab-capture:1.0 |
| capture container wrote a non-empty PCAP | PASS | 2287 bytes |
| capture point observed the Juice Shop HTTP request | PASS | /rest/products/search?q=apple |
| Suricata image available | PASS | jasonish/suricata:8.0 |
| Suricata configuration present | PASS | /var/jenkins_home/workspace/scenario-b-security/project2/scenario-b/security/ids/suricata.yaml |
| local rule file present | PASS | /var/jenkins_home/workspace/scenario-b-security/project2/scenario-b/security/ids/rules/scenario-b-local.rules |
| SID 1000001 defined in the local rules | PASS | sid:1000001 |
| Suricata accepts the configuration (suricata -T) | PASS | Info: detect: 1 signatures processed. 0 are IP-only rules, 0 are inspecting packet payload, 1 inspect application layer, 0 are decoder event only \| Notice: suricata: Configuration provided was successfully loaded. Exiting. \| Warning: running as root due to missing capabilities |
| SID 1000001 is loaded by the active rule set | PASS | 1 rules successfully loaded |
| jq available | PASS | jq-1.7 |
| tshark available | PASS | TShark (Wireshark) 4.4.19. |
| python3 available | PASS | Python 3.13.5 |
| required scripts present and executable | PASS | verify-phase1.sh, preflight.py |
| aquasec/trivy:0.75.0 available | PASS | aquasec/trivy:0.75.0 |
| anchore/syft:v1.52.0 available | PASS | anchore/syft:v1.52.0 |
| Trivy reports a version | PASS | Version: 0.75.0 |
| Trivy vulnerability database available | PASS | database ready |
| Syft reports a version | PASS | Application:   syft |

## Versions

```json
{
  "docker_cli": "Docker version 29.9.2, build a82e528",
  "docker_server": "29.9.2",
  "images": {
    "anchore/syft:v1.52.0": "sha256:500e2d872ac019436926e8322b4fc1f39441d94d21f6f4046c6ff29b30e8cb02",
    "aquasec/trivy:0.75.0": "sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa",
    "bkimminich/juice-shop:v20.2.0": "sha256:8739101ade29358abb5469ee66ae78e582c97ed0a5543a4ad102e5fa5193526b",
    "ghcr.io/zaproxy/zaproxy:stable": "sha256:030d3df57735dacbb83464854758e674dd9ad01d79d12a129a8e58b1fd384238",
    "jasonish/suricata:8.0": "sha256:d5a3a1785299ab40918d465e54fedf8e3afeeedba76bb64b0cc74dbc20bda2c3",
    "telecom-lab-capture:1.0": "sha256:f181d3b53dbb1c0577e420bae65168a15c2acf70af2657fb5d08e24322195c9f",
    "telecom-lab-jenkins:2.580.1-jdk21": "sha256:9e979ae059833564c426bf55d7298efdec00900ac9e9682f33a311aef0432480",
    "telecom-lab-selenium:1.0": "sha256:ab4040ea291ea6c08e71b311d9569fb141072d0831156773948f05164a1939c1"
  },
  "jenkins_plugins": {
    "antisamy-markup-formatter": "173.v680e3a_b_69ff3",
    "apache-httpcomponents-client-4-api": "4.5.14-269.vfa_2321039a_83",
    "asm-api": "9.11.1-226.vff833a_e4c58e",
    "authentication-tokens": "1.144.v5ff4a_5ec5c33",
    "bouncycastle-api": "2.30.1.86.2-310.v4655f6742752",
    "branch-api": "2.1303.v9f3b_95dc329d",
    "caffeine-api": "3.3.1-214.v18eb_56b_34920",
    "cloudbees-folder": "6.1107.v31f8955765c8",
    "commons-lang3-api": "3.21.0-122.v6a_ea_4fd34049",
    "commons-text-api": "1.15.0-218.va_61573470393",
    "credentials": "1514.vb_01eb_014e7d4",
    "credentials-binding": "728.v902a_273b_8947",
    "display-url-api": "2.217.va_6b_de84cc74b_",
    "docker-commons": "477.v289085a_b_6896",
    "docker-workflow": "653.v2f2c08eff0ec",
    "durable-task": "686.v80ff80875b_82",
    "git": "5.11.0",
    "git-client": "6.6.1",
    "gson-api": "2.15.0-212.v085f60a_8093b_",
    "htmlpublisher": "429",
    "instance-identity": "203.v15e81a_1b_7a_38",
    "ionicons-api": "94.vcc3065403257",
    "jackson-annotations2-api": "2.22-19.v10a_a_582ea_26e",
    "jackson2-api": "2.22.4-449.v4ee9f4ec4123",
    "jakarta-activation-api": "2.1.4-1",
    "jakarta-mail-api": "2.1.5-1",
    "jakarta-xml-bind-api": "4.0.9-19.v2b_a_5b_44d9a_1c",
    "javax-activation-api": "1.2.0-8",
    "jaxb": "2.3.9-143.v5979df3304e6",
    "joda-time-api": "2.15.1-211.ve499f52b_da_33",
    "json-api": "20260814-226.v20f9685d642c",
    "mailer": "534.v1b_36f5864073",
    "mina-sshd-api-common": "2.19.0-192.v2b_a_7b_2c1dc71",
    "mina-sshd-api-core": "2.19.0-192.v2b_a_7b_2c1dc71",
    "pipeline-build-step": "601.v6d4c6d1a_9dc7",
    "pipeline-groovy-lib": "822.vc95f70dea_db_7",
    "pipeline-input-step": "560.v56198a_642157",
    "pipeline-milestone-step": "152.v6e22b_8cfc66c",
    "pipeline-model-api": "2.2293.v6e7193cec599",
    "pipeline-model-definition": "2.2293.v6e7193cec599",
    "pipeline-model-extensions": "2.2293.v6e7193cec599",
    "pipeline-stage-step": "345.va_96187909426",
    "pipeline-stage-tags-metadata": "2.2293.v6e7193cec599",
    "plain-credentials": "199.v9f8e1f741799",
    "scm-api": "728.vc30dcf7a_0df5",
    "script-security": "1436.v1082791135e4",
    "snakeyaml-api": "2.7-152.vc672728cf536",
    "ssh-credentials": "372.va_250881b_08cd",
    "structs": "362.va_b_695ef4fdf9",
    "timestamper": "1.30",
    "variant": "70.va_d9f17f859e0",
    "woodstox-core-api": "7.3.0-16.v017f30ed004c",
    "workflow-aggregator": "608.v67378e9d3db_1",
    "workflow-api": "1429.v7a_1b_efb_a_f7c5",
    "workflow-basic-steps": "1129.v60e3c7e6654d",
    "workflow-cps": "4403.v471713a_cea_19",
    "workflow-durable-task-step": "1479.v56e587f413a_7",
    "workflow-job": "1622.vc41c189cb_e5f",
    "workflow-multibranch": "842.v3a_b_59b_57b_e6e",
    "workflow-scm-step": "487.v41313a_96b_65d",
    "workflow-step-api": "724.v538c2362b_dfb_",
    "workflow-support": "1028.vc22910142650"
  },
  "jq": "jq-1.7",
  "juice_shop": "20.2.0",
  "python3": "Python 3.13.5",
  "syft": "Application:   syft",
  "trivy": "Version: 0.75.0",
  "tshark": "TShark (Wireshark) 4.4.19.",
  "zap": "2.17.0"
}
```
