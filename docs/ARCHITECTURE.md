# Architecture

```
camera / tap ──► perception adapter ──► Frame(detections: track, class, zone, xy, hole)
                                              │
                                              ▼
                                  Session (reconciler + policy)
                       identity · safety kernel · ordering · exceptions
                                              │ append only
                                              ▼
                        EventLog (SQLite, hash chain, UPDATE/DELETE blocked)
                                              │ fold
                                              ▼
                  ObjectGraph ──► queries ──► Agent (graph / Muse Wonder) ──► voice, overlay
                                              │
                                              ▼
                       invariants ──► passport gate ──► Ed25519 signature
```

**Truth lives in the log.** The graph is a projection; a new process rebuilds it from events. Models never write to it.

**Perception seam.** `Sam31Perception` needs a `SamBackend.track(image, prompts) -> [RawTrack]`. `ZoneMap` turns boxes into `device | hand | tray_N | bench`. A track's box centre breaks re-ID ties between a dropped detection and a new track.

**Reasoning seam.** `WonderAgent` takes a client with `complete(messages, tools) -> {"tool", "args"} | {"text"}`. Its tools are read-only plus `propose_step`, which accepts only ids the graph lists as legal.

**Safety kernel.** Four rules in a module-level tuple, evaluated before every removal. A violation is recorded and announced; the technician can acknowledge it, and the acknowledgement appears on the passport.

**Passport.** Signed body includes the event-chain head, so editing either the passport or the log breaks verification. The embedded public key proves integrity, not identity.
