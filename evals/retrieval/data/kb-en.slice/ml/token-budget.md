+++
title = "LLM token budget"
aliases = []
tags = ["ml", "llm"]
extends = []
supersedes = []
+++

Prompts to the language model must fit a 32k token context window.

- Reserve 4k tokens for the model's answer.
- Truncate retrieved documents before the system prompt.
