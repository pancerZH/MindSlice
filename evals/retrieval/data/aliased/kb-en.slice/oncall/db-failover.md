+++
title = "Database failover"
aliases = ["high availability", "switchover", "standby", "DB outage", "数据库切换", "主备切换", "主从切换"]
tags = ["oncall", "database"]
extends = []
supersedes = []
+++

The primary database fails over to the replica in another zone.

- Failover is manual and needs two engineers.
- Expect about 2 minutes of write downtime.
