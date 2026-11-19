"""A what-if agent: a language model that answers questions about pit strategy by calling the simulator's tools.

The model never computes anything itself. It decides which tool to call, with what arguments, and then explains the result in
plain words; agent_eval.py checks that it does exactly that. Needs the optional `anthropic` package (uv sync --extra agent).
"""
import json

from pitwall.agent_tools import TOOL_DEFINITIONS, run_tool

DEFAULT_MODEL = "claude-sonnet-5-5"

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
refits agree, the interval). A negative gap means faster than the real strategy.
6. When you give a comparison, include one sentence on how far to trust it, using the tool's verdict and caveats.
Keep answers under about 150 words, in plain language."""


def run_agent(question: str, ctx: dict, client, model: str = DEFAULT_MODEL, max_turns: int = 6, max_tokens: int = 4000,
              effort: str | None = "medium", tool_runner=run_tool) -> dict:
    '''
    Answers one question, calling tools as needed.

    question: the user's question
    ctx: agent_tools.load_context result
    client: an anthropic.Anthropic client (anything with .messages.create works, which is how the tests run it)
    model: model id; effort: output_config effort level, or None to leave it at the model's default
    max_turns: most model calls before giving up; max_tokens: output limit per call
    tool_runner: how a tool call is executed (agent_tools.run_tool); replaced in tests

    returns: dict with "answer" (text), "tool_calls" (each {"name", "input", "result"}), "stop_reason" (the model's last
    stop reason, "max_turns" if it never finished, "refusal" if it declined), "turns" and "usage" (summed input and output
    tokens). An unfinished or refused run has an empty "answer"; a run cut off by max_tokens keeps the partial text.
    '''
    messages = [{"role": "user", "content": question}]
    tool_calls, usage = [], {"input_tokens": 0, "output_tokens": 0}
    for turn in range(1, max_turns + 1):
        request = {"model": model, "max_tokens": max_tokens, "system": SYSTEM_PROMPT, "tools": TOOL_DEFINITIONS,
                   "messages": messages}
        if effort:
            request["output_config"] = {"effort": effort}
        response = client.messages.create(**request)
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                output = tool_runner(ctx, block.name, block.input)
                tool_calls.append({"name": block.name, "input": dict(block.input), "result": output})
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(output, ensure_ascii=False),
                                "is_error": output.get("error") in ("unknown_tool", "bad_input")})
            messages.append({"role": "user", "content": results})      # every result of one turn in a single message
            continue
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        text = "".join(block.text for block in response.content if block.type == "text")
        return {"answer": "" if response.stop_reason == "refusal" else text, "tool_calls": tool_calls,
                "stop_reason": response.stop_reason, "turns": turn, "usage": usage}
    return {"answer": "", "tool_calls": tool_calls, "stop_reason": "max_turns", "turns": max_turns, "usage": usage}
