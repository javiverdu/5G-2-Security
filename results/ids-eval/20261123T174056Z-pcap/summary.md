# Signature IDS on the ISCX 14 June capture

- Suricata run: `/home/x0riso/.hermes/cache/scratch/suri-out/eve.json` (612.2 MB of eve.json)
- Ruleset: ET Open (suricata-update snapshot)
- Alerts: **25771** total, of which **9** carry a DoS/flood/brute/scan signature
- Flood window 2010-06-14T20:30 .. 2010-06-14T21:35: 641 alerts, of which **0** DoS-flavoured
- Alert window: 2010-06-14T03:01:09.534853+0000 .. 2010-06-15T03:01:04.094598+0000
- Ground truth (XML): 3776 attack flows from 10 sources, window 2010-06-13T23:59:17 .. 2010-06-14T22:59:17
- Attack sources with a DoS-flavoured alert: **0 of 10**

## Top signatures

| SID and message | alerts |
|---|---|
| `2221036 SURICATA HTTP Response excessive header repetition` | 21917 |
| `2260002 SURICATA Applayer Detect protocol only one direction` | 2502 |
| `2000334 ET P2P BitTorrent peer sync` | 417 |
| `2030384 ET HUNTING Suspicious Terse Request for .bmp` | 208 |
| `2210054 SURICATA STREAM excessive retransmissions` | 111 |
| `2210063 SURICATA STREAM 3way handshake excessive different SYNs` | 66 |
| `2102181 GPL P2P BitTorrent transfer` | 62 |
| `2012059 ET WEB_CLIENT Hex Obfuscation of document.write % Encoding` | 34 |
| `2013504 ET INFO GNU/Linux APT User-Agent Outbound likely related to package management` | 30 |
| `2036303 ET HUNTING Terse Unencrypted Request for Google - Likely Connectivity Check` | 24 |

## DoS-flavoured signatures

| SID and message | alerts |
|---|---|
| `2001219 ET SCAN Potential SSH Scan` | 9 |

## Top alert sources

| source | alerts |
|---|---|
| `142.166.14.78` | 1295 |
| `142.166.14.70` | 1192 |
| `88.208.248.162` | 781 |
| `67.15.47.4` | 780 |
| `142.166.14.85` | 752 |
| `173.222.140.91` | 716 |
| `192.168.2.107` | 622 |
| `72.246.31.51` | 501 |
| `142.166.14.77` | 496 |
| `72.246.30.144` | 484 |

## Labelled attack sources (XML)

| source | attack flows |
|---|---|
| `192.168.2.112` | 1690 |
| `192.168.2.113` | 630 |
| `192.168.3.115` | 507 |
| `192.168.1.101` | 471 |
| `192.168.2.106` | 369 |
| `192.168.3.117` | 104 |
| `218.108.130.167` | 2 |
| `200.46.125.39` | 1 |
| `217.140.88.36` | 1 |
| `200.153.221.172` | 1 |
