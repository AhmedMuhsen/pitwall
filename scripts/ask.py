"""Ask the what-if agent a question (OpenRouter by default):

  export OPENROUTER_API_KEY=sk-or-...
  uv run python scripts/ask.py "What if Leclerc had pitted on lap 20 at Monza 2024?" -v

Each question costs a fraction of a cent to a few cents, depending on the model. --provider anthropic uses the Anthropic API
directly instead (needs: uv sync --extra agent, and ANTHROPIC_API_KEY). -v prints every tool call and its result."""
import argparse
import json
import sys

from pitwall.agent import DEFAULT_MODELS, run_agent
from pitwall.agent_tools import load_context
from pitwall.llm import LLMError, make_client


def main():
    parser = argparse.ArgumentParser(description="Ask the PitWall what-if agent a question.")
    parser.add_argument("question")
    parser.add_argument("--provider", choices=["openrouter", "anthropic"], default="openrouter")
    parser.add_argument("--model", default=None, help="model id in the provider's naming (default: Sonnet 5.5)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show the tool calls and their results")
    args = parser.parse_args()
    model = args.model or DEFAULT_MODELS[args.provider]
    try:
        result = run_agent(args.question, load_context(), make_client(args.provider), model=model)
    except LLMError as error:
        sys.exit(f"{type(error).__name__}: {error}")
    if args.verbose:
        for call in result["tool_calls"]:
            print(f"[tool] {call['name']}({json.dumps(call['input'], ensure_ascii=False)})")
            print("       ->", json.dumps(call["result"], ensure_ascii=False)[:600])
    print(result["answer"] or f"(no answer: stopped with {result['stop_reason']})")
    cost = result["usage"]["cost_usd"]
    print(f"\n[{model}; {result['turns']} model calls, {result['usage']['input_tokens']} input and "
          f"{result['usage']['output_tokens']} output tokens" + (f", ${cost:.4f}]" if cost is not None else "]"))


if __name__ == "__main__":
    main()
