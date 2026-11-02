# Eval report

> **Synthetic.** These sessions come from the bench simulator, not a camera. They test the memory, safety and verification layers under injected dropout and tracker churn. Replace `eval/sessions/` with recorded clips (see `cairn/evaluation.py`) for evidence about real perception.

| Metric | Value | Target | Result |
|---|---|---|---|
| part_detection_recall | 1.0 | >= 0.95 | PASS |
| id_switch_rate | 0.033 | <= 0.05 | PASS |
| missing_part_latency_s_max | 2.75 | <= 5.0 | PASS |
| scripted_fault_catch_rate | 1.0 | >= 1.0 | PASS |
| false_alarm_rate_clean_runs | 0.0 | <= 0.1 | PASS |

Every event chain verified: True. Replaying the recording reproduces the original event log byte for byte: True.

| Run | Setup | Parts | Tracked | ID switches | Caught | Missing-part latency | Spurious | Closes clean |
|---|---|---|---|---|---|---|---|---|
| 01 | clean | 29 | 29 | 0 | n/a | - | - | yes |
| 02 | clean | 29 | 29 | 0 | n/a | - | - | yes |
| 03 | clean | 29 | 29 | 0 | n/a | - | - | yes |
| 04 | clean | 29 | 29 | 0 | n/a | - | - | yes |
| 05 | dropped screw | 29 | 29 | 15 | drop:yes | 2.75s | - | yes |
| 06 | skipped battery step | 29 | 29 | 0 | skip_battery:yes | - | - | yes |
| 07 | wrong screw | 29 | 29 | 0 | wrong_screw:yes | - | - | yes |
| 08 | stray part | 29 | 29 | 0 | extra_part:yes | - | - | no |
| 09 | three faults | 29 | 29 | 10 | skip_battery:yes, drop:yes, wrong_screw:yes | 2.75s | - | yes |
| 10 | all faults, bad lighting | 29 | 29 | 25 | skip_battery:yes, drop:yes, extra_part:yes, wrong_screw:yes | 2.75s | - | no |

## Imperfections, honestly

- **Run 05 (dropped screw):** 15 identity switches between interchangeable screws after the tracker issued new ids; every part still reconciled and the job closed clean.
- **Run 09 (three faults):** 10 identity switches between interchangeable screws after the tracker issued new ids; every part still reconciled and the job closed clean.
- **Run 10 (all faults, bad lighting):** 25 identity switches between interchangeable screws after the tracker issued new ids; every part still reconciled and the job stopped at the close gate.
- Runs 08, 10 stop at the close gate by design: a stray part is an open exception until the technician resolves it with a note. They then close, or close with exceptions.
- No missed faults and no false alarms in this set. Real footage will be harsher; treat this as a floor on the harness, not a result.
