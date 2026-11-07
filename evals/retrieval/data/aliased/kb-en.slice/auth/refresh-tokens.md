+++
title = "Refresh tokens"
aliases = ["remember me", "stay logged in", "long-lived token", "replay attack", "OAuth", "刷新令牌", "令牌续期"]
tags = ["auth"]
extends = []
supersedes = []
+++

Refresh tokens are single use and rotate on every renewal.

- A refresh token lives for 14 days.
- Reusing a refresh token revokes the whole session family.
