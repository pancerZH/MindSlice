+++
title = "LLM token budget"
aliases = ["context length", "max tokens", "token limit", "prompt too long", "上下文窗口", "上下文长度", "token上限"]
tags = ["ml", "llm"]
extends = []
supersedes = []
+++

Prompts to the language model must fit a 32k token context window.

- Reserve 4k tokens for the model's answer.
- Truncate retrieved documents before the system prompt.
