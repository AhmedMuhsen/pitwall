"""Ask the what-if agent a question:  uv run --extra agent python scripts/ask.py "What if Leclerc had pitted on lap 20 at Monza 2024?"

Needs an Anthropic API key (ANTHROPIC_API_KEY, or `ant auth login`); each question costs a small amount of API credit.
-v prints every tool call and its result."""
import argparse
import json
import sys

from pitwall.agent import DEFAULT_MODEL, run_agent
from pitwall.agent_tools import load_context


def main():
    parser = argparse.ArgumentParser(description="Ask the PitWall what-if agent a question.")
    parser.add_argument("question")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model id (default {DEFAULT_MODEL})")
    parser.add_argument("-v", "--verbose", action="store_true", help="show the tool calls and their results")
    args = parser.parse_args()
    try:
        import anthropic
    except ImportError:
        sys.exit("The anthropic package isn't installed. Run: uv sync --extra agent")
    client = anthropic.Anthropic()
    try:
        result = run_agent(args.question, load_context(), client, model=args.model)
    except TypeError as error:          # the SDK raises TypeError on the first request when it finds no credentials
        if "authentication" not in str(error):
            raise
        sys.exit("No Anthropic credentials found: export ANTHROPIC_API_KEY=..., or run `ant auth login`.")
    except anthropic.AuthenticationError:
        sys.exit("Authentication failed: check ANTHROPIC_API_KEY, or run `ant auth login`.")
    if args.verbose:
        for call in result["tool_calls"]:
            print(f"[tool] {call['name']}({json.dumps(call['input'], ensure_ascii=False)})")
            print("       ->", json.dumps(call["result"], ensure_ascii=False)[:600])
    print(result["answer"] or f"(no answer: stopped with {result['stop_reason']})")
    print(f"\n[{args.model}; {result['turns']} model calls, {result['usage']['input_tokens']} input and "
          f"{result['usage']['output_tokens']} output tokens]")


if __name__ == "__main__":
    main()
