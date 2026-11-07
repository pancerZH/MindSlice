+++
title = "Canary releases"
aliases = []
tags = ["deploy", "release"]
extends = []
supersedes = []
+++

New versions first receive 5% of traffic for 30 minutes.

- The canary is promoted automatically if error rates stay flat.
- Latency regressions above 10% abort the canary.
