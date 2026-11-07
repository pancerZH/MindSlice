+++
title = "Canary releases"
aliases = ["progressive delivery", "staged rollout", "traffic shifting", "灰度发布", "金丝雀发布", "小流量"]
tags = ["deploy", "release"]
extends = []
supersedes = []
+++

New versions first receive 5% of traffic for 30 minutes.

- The canary is promoted automatically if error rates stay flat.
- Latency regressions above 10% abort the canary.
