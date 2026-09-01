# ADR 0007 — No LLM Provider in Core

- Status: Proposed

## Decision

Agnara core does not call OpenAI, Anthropic, Gemini, local models, or any other LLM provider.

## Rationale

Agent-native means an agent can discover, reason about and safely invoke capabilities.

It does not mean the capability runtime must own reasoning or model orchestration.

LLM/agent-framework integrations belong in optional packages.
