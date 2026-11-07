+++
title = "Schema migrations"
aliases = ["DDL", "parallel change", "zero-downtime", "rename a column", "数据迁移", "表结构变更", "数据库变更"]
tags = ["data", "database"]
extends = []
supersedes = []
+++

Schema changes follow the expand and contract pattern.

- Never drop a column in the same release that stops using it.
- Large backfills run in batches of 10,000 rows.
