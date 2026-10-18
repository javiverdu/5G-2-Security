# Step 3 — Comparative results (mean of the repetitions)

| Condition | icmp_rtt_avg (ms) | http_time_avg (s) | tcp_throughput (Mbit/s) | udp_throughput (Mbit/s) | udp_loss (%) | udp_jitter (ms) | tcp_retransmissions (count) | tcp_retransmissions_sender (count) |
|---|---|---|---|---|---|---|---|---|
| baseline | 0.081 | 0.001 | 38048.555 | 10.000 | 0.026 | 0.026 | 0.000 | 0.000 |
| delay | 157.803 | 0.218 | 140.803 | 10.001 | 0.039 | 6.316 | 3.000 | 2.000 |
| loss | 0.086 | 0.015 | 4434.393 | 10.002 | 1.865 | 0.037 | 21.000 | 137.000 |
| rate | 14.612 | 0.002 | 18.964 | 10.001 | 0.000 | 0.104 | 0.000 | 0.000 |
