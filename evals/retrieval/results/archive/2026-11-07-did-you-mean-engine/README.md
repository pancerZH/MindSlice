# Record: the engine with `did_you_mean` (2026-11-07)

The results as read on the engine whose `search()` also returned `did_you_mean` suggestions (source
digest `f8e62ecdcb2ea9683593c61959e81f81394c1db8605c2afbe19ff35e9f1236de`), kept unchanged. Lines L18 to
L24 were first read here. L23 and L24 (the `suggest-retry` system) led to removing `did_you_mean`; see
the decision and the ledger in [PLAN.md](../../../PLAN.md). Every other system's rankings are identical
on the engine without it.
