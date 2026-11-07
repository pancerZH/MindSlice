+++
title = "Session tokens"
aliases = ["session timeout", "idle timeout", "auto logout", "access token", "会话令牌", "登录超时", "会话过期"]
tags = ["auth", "security"]
extends = []
supersedes = []
+++

Web sessions use opaque bearer tokens that expire after 15 minutes.

- The token expiration is 15 minutes of inactivity.
- Clients renew a session with a refresh token, see [[auth/refresh-tokens]].
- Tokens are sent in the Authorization header, never in URLs.
