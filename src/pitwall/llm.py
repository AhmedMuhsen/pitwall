"""Language-model clients behind one small interface, so the agent doesn't care which provider answers.

Both clients have a `complete(...)` method that takes the conversation in a provider-neutral form and returns a `Completion`:

  user message       {"role": "user", "content": "text"}
  assistant message  {"role": "assistant", "text": "...", "tool_calls": [ToolCall, ...], "raw": <provider-native content>}
  tool results       {"role": "tool", "results": [{"id": ..., "content": "json text", "is_error": False}, ...]}

OpenRouterClient talks to OpenRouter's chat-completions API with the standard library only (no extra dependency): one key,
many models, billed by usage. AnthropicClient wraps the official `anthropic` SDK (optional extra: uv sync --extra agent).
"""
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRYABLE = {408, 429, 500, 502, 503, 504}


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Completion:
    """One model reply. stop is "end_turn", "tool_use", "max_tokens", "refusal", "pause_turn" or "error"; usage has
    input_tokens, output_tokens and cost_usd (None when the provider doesn't report it); raw is the provider's own assistant
    content, sent back unchanged on the next turn."""
    text: str
    tool_calls: list
    stop: str
    usage: dict
    raw: object


class LLMError(Exception):
    """A request failed in a way the caller can't fix by retrying."""


class AuthenticationFailed(LLMError):
    """The API key is missing, wrong or disabled."""


class OutOfCredits(LLMError):
    """The account (or the key's limit) has no credit left."""


# ---------------------------------------------------------------- OpenRouter (OpenAI-style chat completions)

def openai_tools(tools: list[dict]) -> list[dict]:
    '''Anthropic-style tool definitions (name, description, input_schema) as OpenAI-style function tools.'''
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools]


def openai_messages(system: str, messages: list[dict]) -> list[dict]:
    '''The neutral conversation as OpenAI-style messages (system first; each tool result is its own "tool" message).'''
    out = [{"role": "system", "content": system}]
    for message in messages:
        if message["role"] == "user":
            out.append({"role": "user", "content": message["content"]})
        elif message["role"] == "assistant":
            entry = {"role": "assistant", "content": message["text"] or None}
            if message["tool_calls"]:
                entry["tool_calls"] = [{"id": c.id, "type": "function",
                                        "function": {"name": c.name, "arguments": json.dumps(c.input, ensure_ascii=False)}}
                                       for c in message["tool_calls"]]
            raw = message.get("raw")
            if isinstance(raw, dict) and raw.get("reasoning_details"):
                entry["reasoning_details"] = raw["reasoning_details"]      # reasoning models want this echoed back with tool calls
            out.append(entry)
        else:
            out += [{"role": "tool", "tool_call_id": r["id"], "content": r["content"]} for r in message["results"]]
    return out


def parse_openai_response(body: dict) -> Completion:
    '''
    An OpenRouter chat-completions response as a Completion.

    raises LLMError if the body has no choices (a failed generation can come back as HTTP 200 with only an "error" object).
    '''
    if not body.get("choices"):
        error = body.get("error") or {}
        raise LLMError(f"no choices in the response: {error.get('message', body)!r}")
    choice = body["choices"][0]
    message = choice.get("message") or {}
    calls = []
    for call in message.get("tool_calls") or []:
        arguments = call["function"].get("arguments") or "{}"
        try:
            parsed = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        except ValueError:
            parsed = {"_unparsed_arguments": arguments}          # the tool will report bad_input
        calls.append(ToolCall(call["id"], call["function"]["name"], parsed))
    finish = choice.get("finish_reason")
    stop = ("tool_use" if calls else {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal",
                                      "error": "error"}.get(finish, "end_turn"))
    usage = body.get("usage") or {}
    return Completion(text=message.get("content") or "", tool_calls=calls, stop=stop,
                      usage={"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0),
                             "cost_usd": usage.get("cost")}, raw=message)


class OpenRouterClient:
    '''
    OpenRouter's chat-completions API, standard library only.

    api_key: defaults to the OPENROUTER_API_KEY environment variable
    attempts: tries per request for transient failures (429, 5xx, timeouts), with exponential backoff that honours Retry-After
    opener, sleep: replaceable for tests

    complete raises AuthenticationFailed (no or bad key), OutOfCredits (HTTP 402) or LLMError (anything else that retrying
    won't fix, e.g. a model that doesn't support tools).
    '''

    def __init__(self, api_key: str | None = None, attempts: int = 4, opener=urllib.request.urlopen, sleep=time.sleep,
                 url: str = OPENROUTER_URL):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.attempts, self.opener, self.sleep, self.url = attempts, opener, sleep, url

    def complete(self, model: str, system: str, messages: list[dict], tools: list[dict], max_tokens: int,
                 effort: str | None = None) -> Completion:
        if not self.api_key:
            raise AuthenticationFailed("No OpenRouter key: export OPENROUTER_API_KEY=sk-or-...")
        payload = {"model": model, "messages": openai_messages(system, messages), "tools": openai_tools(tools),
                   "max_tokens": max_tokens}
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://github.com/AhmedMuhsen/pitwall", "X-OpenRouter-Title": "PitWall"})
        for attempt in range(1, self.attempts + 1):
            retry_after, problem = None, None
            try:
                with self.opener(request, timeout=120) as response:
                    body = json.loads(response.read())
                if "error" in body and not body.get("choices"):
                    code = (body["error"] or {}).get("code")
                    if code in RETRYABLE:
                        problem = f"provider error {code}"
                    else:
                        raise LLMError(f"OpenRouter error {code}: {(body['error'] or {}).get('message')}")
                else:
                    return parse_openai_response(body)
            except urllib.error.HTTPError as error:
                detail = _error_message(error)
                if error.code == 402:
                    raise OutOfCredits(detail) from error
                if error.code in (401, 403):
                    raise AuthenticationFailed(detail) from error
                if error.code not in RETRYABLE:
                    raise LLMError(f"HTTP {error.code}: {detail}") from error
                retry_after, problem = error.headers.get("Retry-After") if error.headers else None, f"HTTP {error.code}: {detail}"
            except (urllib.error.URLError, TimeoutError) as error:
                problem = f"network error: {error}"
            if attempt == self.attempts:
                raise LLMError(f"gave up after {attempt} attempts: {problem}")
            self.sleep(float(retry_after) if retry_after else 2.0 ** attempt)
        raise LLMError("unreachable")


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        return json.loads(error.read())["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return str(error.reason)


# ---------------------------------------------------------------- Anthropic (official SDK)

def anthropic_messages(messages: list[dict]) -> list[dict]:
    '''The neutral conversation as Anthropic Messages API messages (all tool results of a turn in one user message).'''
    out = []
    for message in messages:
        if message["role"] == "user":
            out.append({"role": "user", "content": message["content"]})
        elif message["role"] == "assistant":
            out.append({"role": "assistant", "content": message["raw"]})       # thinking blocks must go back unchanged
        else:
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"], "is_error": r["is_error"]}
                for r in message["results"]]})
    return out


class AnthropicClient:
    '''The Anthropic Messages API through the official SDK (needs: uv sync --extra agent). `client` can be any object with
    .messages.create, which is how the tests use it.'''

    def __init__(self, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client

    def complete(self, model: str, system: str, messages: list[dict], tools: list[dict], max_tokens: int,
                 effort: str | None = None) -> Completion:
        request = {"model": model, "max_tokens": max_tokens, "system": system, "tools": tools,
                   "messages": anthropic_messages(messages)}
        if effort:
            request["output_config"] = {"effort": effort}
        response = self.client.messages.create(**request)
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"]
        stop = {"tool_use": "tool_use", "end_turn": "end_turn", "max_tokens": "max_tokens", "refusal": "refusal",
                "pause_turn": "pause_turn"}.get(response.stop_reason, "end_turn")
        return Completion(text="".join(b.text for b in response.content if b.type == "text"), tool_calls=calls, stop=stop,
                          usage={"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
                                 "cost_usd": None}, raw=response.content)


def make_client(provider: str):
    '''The client for "openrouter" (default; needs OPENROUTER_API_KEY) or "anthropic" (needs the extra and ANTHROPIC_API_KEY).'''
    if provider == "openrouter":
        return OpenRouterClient()
    if provider == "anthropic":
        try:
            return AnthropicClient()
        except ImportError as error:
            raise LLMError("The anthropic package isn't installed. Run: uv sync --extra agent") from error
    raise LLMError(f"unknown provider {provider!r}: use openrouter or anthropic")
