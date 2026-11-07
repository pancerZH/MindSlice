+++
title = "JWT sessions"
aliases = []
tags = ["auth"]
extends = []
supersedes = ["@kb-en/auth/session-tokens"]
+++

Sessions now use signed JWTs that expire after 30 minutes.

- The JWT TTL is 30 minutes.
- Renewal still uses refresh tokens.
- Tokens stay in the Authorization header.
