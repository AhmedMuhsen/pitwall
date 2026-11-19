"""A what-if agent: a language model that answers questions about pit strategy by calling the simulator's tools.

The model never computes anything itself. It decides which tool to call, with what arguments, and then explains the result in
plain words; agent_eval.py checks that it does exactly that. Which provider answers is up to the client (llm.py).
"""
import json

from pitwall.agent_tools import TOOL_DEFINITIONS, run_tool

DEFAULT_MODELS = {"openrouter": "anthropic/claude-sonnet-5.5", "anthropic": "claude-sonnet-5-5"}
DEFAULT_MODEL = DEFAULT_MODELS["openrouter"]

SYSTEM_PROMPT = """You answer questions about Formula 1 pit strategy. You have a lap-time simulator built from 2023-2025 race \
data, and you can reach it only through your tools.

Rules:
1. Every number in your answer must come from a tool result. Never estimate, recall or work out a new number: no sums or \
differences of tool numbers (rounding a tool number is fine). Quote the gaps, times and intervals the tools give you.
2. To compare strategies, call compare_strategy. If the user names a specific strategy (tyre compounds and pit laps), pass it; \
otherwise leave compounds and pit_laps empty. If you are unsure a race or car is available, call list_races or list_cars first.
3. If the question doesn't say which race or which car, ask one short clarifying question instead of guessing, and don't call \
compare_strategy.
4. If a tool returns an error, tell the user plainly what it says, in your own words, and what is available instead. Don't work \
around it and don't invent an answer. The simulator cannot answer questions about finishing positions, comparing drivers, the \
2022 or 2026 seasons, wet races, red-flagged races, or what would happen if a safety car had come out: say so.
5. Never call a strategy optimal, best or guaranteed. Report what the model prefers and how sure it is (the verdict, how many \
refits agree, the interval). A negative gap means faster than the real strategy. "range_over_pit_loss_assumptions_s" is how the gap moves if the pit-stop cost is assumed lower or higher; "faster_in_refits" is a separate check (refitting the model on subsets of races). Don't present them as one range.
6. When you give a comparison, include one sentence on how far to trust it, using the tool's verdict and caveats.
Keep answers under about 150 words, in plain language."""


def run_agent(question: str, ctx: dict, client, model: str = DEFAULT_MODEL, max_turns: int = 6, max_tokens: int = 4000,
              effort: str | None = "medium", tool_runner=run_tool) -> dict:
    '''
    Answers one question, calling tools as needed.

    question: the user's question
    ctx: agent_tools.load_context result
    client: an llm.OpenRouterClient or llm.AnthropicClient (anything with a compatible .complete(); the tests pass a script)
    model: model id in that provider's naming; effort: reasoning effort where the provider supports it, or None
    max_turns: most model calls before giving up; max_tokens: output limit per call
    tool_runner: how a tool call is executed (agent_tools.run_tool); replaced in tests

    returns: dict with "answer" (text), "tool_calls" (each {"name", "input", "result"}), "stop_reason" (the last stop reason:
    "end_turn", "max_tokens", "refusal", "error", or "max_turns" if it never finished), "turns" and "usage" (summed
    "input_tokens" and "output_tokens", and "cost_usd" when the provider reports it, else None). An unfinished, refused or failed
    run has an empty "answer"; a run cut off by max_tokens keeps the partial text.
    '''
    messages = [{"role": "user", "content": question}]
    tool_calls = []
    usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": None}
    for turn in range(1, max_turns + 1):
        reply = client.complete(model=model, system=SYSTEM_PROMPT, messages=messages, tools=TOOL_DEFINITIONS,
                                max_tokens=max_tokens, effort=effort)
        usage["input_tokens"] += reply.usage["input_tokens"]
        usage["output_tokens"] += reply.usage["output_tokens"]
        if reply.usage.get("cost_usd") is not None:
            usage["cost_usd"] = (usage["cost_usd"] or 0.0) + reply.usage["cost_usd"]

        if reply.stop == "tool_use":
            messages.append({"role": "assistant", "text": reply.text, "tool_calls": reply.tool_calls, "raw": reply.raw})
            results = []
            for call in reply.tool_calls:
                output = tool_runner(ctx, call.name, call.input)
                tool_calls.append({"name": call.name, "input": dict(call.input), "result": output})
                results.append({"id": call.id, "content": json.dumps(output, ensure_ascii=False),
                                "is_error": output.get("error") in ("unknown_tool", "bad_input")})
            messages.append({"role": "tool", "results": results})      # every result of one turn goes back together
            continue
        if reply.stop == "pause_turn":
            messages.append({"role": "assistant", "text": reply.text, "tool_calls": [], "raw": reply.raw})
            continue
        return {"answer": "" if reply.stop in ("refusal", "error") else reply.text, "tool_calls": tool_calls,
                "stop_reason": reply.stop, "turns": turn, "usage": usage}
    return {"answer": "", "tool_calls": tool_calls, "stop_reason": "max_turns", "turns": max_turns, "usage": usage}
