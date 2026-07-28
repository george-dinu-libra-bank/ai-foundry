"""The local agent — the persona runs in *your* process, against any provider.

This is the honest minimum of what an "agent" is when you strip the marketing:
a persona (instructions + rules), optional retrieved context, and a model call.
No platform required — it works with OpenAI, Anthropic, LM Studio or Foundry,
and it is what runs when AGENT_MODE=local.

Compare with foundry_agent.py, where the same persona is hosted by Azure and the
loop runs on Microsoft's side.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from ..llm import get_llm
from .persona import Persona


@dataclass
class AgentReply:
    text: str
    mode: str                       # "local" | "foundry"
    persona: str
    system_prompt: str              # exactly what was sent as the system message
    prompt_sent: str                # exactly what was sent as the user message
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


EMPTY_CONTEXT = (
    "CONTEXT — retrieved passages:\n"
    "(none — the search ran against the bank's documents and nothing passed the "
    "relevance threshold)\n\n"
    "The knowledge base has no passage covering this question. Say so plainly and "
    "do not answer from general knowledge: an invented answer here is worse than "
    "no answer. Name what the customer could ask instead, if anything in scope is "
    "close.\n\n"
    "QUESTION:\n"
)


def build_user_prompt(question: str, chunks: list[dict],
                      retrieval_attempted: bool = False) -> str:
    """Question alone, question + retrieved passages, or question + an explicit
    statement that retrieval found nothing.

    That third case is the one that matters. Without it, a question whose answer is
    not in the corpus arrives at the model as a bare question with an ungrounded
    system prompt — and the model answers it confidently from what it happens to
    know about banking. Retrieval having found nothing is *information*, and the
    model has to be told.
    """
    if not chunks:
        return (EMPTY_CONTEXT + question) if retrieval_attempted else question
    context = "\n\n".join(
        f"[{i + 1}] (score {c['score']}) {c['text']}" for i, c in enumerate(chunks)
    )
    return (
        "CONTEXT — retrieved passages, most similar first:\n"
        f"{context}\n\n"
        "QUESTION:\n"
        f"{question}"
    )


def run(
    persona: Persona,
    question: str,
    chunks: list[dict] | None = None,
    temperature: float | None = None,
    retrieval_attempted: bool = False,
) -> AgentReply:
    chunks = chunks or []
    # an empty result from a search that *ran* is still a grounded turn: the
    # persona's refusal rules must apply precisely when there is nothing to cite
    system = persona.system_prompt(grounded=bool(chunks) or retrieval_attempted)
    user = build_user_prompt(question, chunks, retrieval_attempted)

    # precedence: explicit request value > persona file > .env default
    temp = temperature if temperature is not None else (
        persona.temperature if persona.temperature is not None else settings.llm_temperature
    )
    max_tokens = persona.max_tokens or settings.llm_max_tokens

    # Reasoning models (the gpt-5 family) spend part of the completion budget thinking
    # before they write. A persona can cap that so short, stylistic answers are not
    # starved of visible output tokens.
    extras = {"reasoning_effort": persona.reasoning_effort} if persona.reasoning_effort else {}

    llm = get_llm()
    result = llm.chat(system=system, user=user, temperature=temp,
                      max_tokens=max_tokens, extras=extras)

    return AgentReply(
        text=result.text,
        mode="local",
        persona=persona.name,
        system_prompt=system,
        prompt_sent=user,
        provider=result.provider,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )
