+++
title = "Schema migrations"
aliases = []
tags = ["data", "database"]
extends = []
supersedes = []
+++

Schema changes follow the expand and contract pattern.

- Never drop a column in the same release that stops using it.
- Large backfills run in batches of 10,000 rows.
