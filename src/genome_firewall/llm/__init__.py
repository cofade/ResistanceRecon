"""Provider-agnostic LLM abstraction (OpenAI primary, MockLLMClient for tests).

Used ONLY for evidence RAG, grounded report narration, and review. Never a source of
a verdict or confidence. Importable only from ``report``/``kb`` — never from the
prediction path (``reader``/``features``/``predictor``).
"""
