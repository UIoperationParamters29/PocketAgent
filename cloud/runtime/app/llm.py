"""Multi-provider LLM adapter.

Most providers (OpenAI, z.ai GLM, OpenRouter, Groq, Mistral, Together, Ollama)
speak the OpenAI Chat Completions API natively, so we use the `openai` SDK
directly against their base_url.

Anthropic and Google Gemini have their own native APIs. Rather than running a
separate LiteLLM proxy process, we adapt them to the same `AsyncIterator` shape
the agent loop expects. The adapter pattern keeps everything in one process.

Provider detection is based on the base_url:
  - api.anthropic.com            → Anthropic native
  - generativelanguage.googleapis.com → Gemini native
  - everything else              → OpenAI-compatible (default)

The agent loop only needs:
  - stream_chat(messages, tools, model, ...) -> AsyncIterator[StreamEvent]
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Optional

# --------------------------------------------------------------------------- #
# Stream event shape (provider-agnostic)
# --------------------------------------------------------------------------- #
@dataclass
class StreamEvent:
    """A single event from the LLM stream."""
    kind: Literal["delta", "tool_call_start", "tool_call_delta", "tool_call_end", "done"]
    # For kind='delta': the text token
    text: str = ""
    # For tool_call_* events:
    tool_index: int = 0
    tool_id: str = ""
    tool_name: str = ""
    tool_args_delta: str = ""
    # For kind='done': the finish_reason
    finish_reason: str = ""


# --------------------------------------------------------------------------- #
# Provider detection
# --------------------------------------------------------------------------- #
def detect_provider(base_url: str) -> str:
    """Return 'anthropic', 'gemini', or 'openai' based on base_url."""
    url = (base_url or "").lower()
    if "api.anthropic.com" in url or "anthropic" in url:
        return "anthropic"
    if "generativelanguage.googleapis.com" in url or "gemini" in url:
        return "gemini"
    return "openai"


# --------------------------------------------------------------------------- #
# OpenAI-compatible streamer (covers OpenAI, z.ai, OpenRouter, Groq, Mistral,
# Together, Ollama, any OpenAI-format endpoint)
# --------------------------------------------------------------------------- #
async def stream_openai(
    *, base_url: str, api_key: str, model: str,
    messages: list[dict], tools: list[dict], max_iterations_hint: int = 25,
) -> AsyncIterator[StreamEvent]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield StreamEvent(kind="delta", text=delta.content)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.id:
                    yield StreamEvent(
                        kind="tool_call_start",
                        tool_index=tc.index,
                        tool_id=tc.id,
                        tool_name=tc.function.name if tc.function else "",
                    )
                if tc.function and tc.function.arguments:
                    yield StreamEvent(
                        kind="tool_call_delta",
                        tool_index=tc.index,
                        tool_args_delta=tc.function.arguments,
                    )
        if chunk.choices[0].finish_reason:
            yield StreamEvent(kind="done", finish_reason=chunk.choices[0].finish_reason)


# --------------------------------------------------------------------------- #
# Anthropic native streamer
# --------------------------------------------------------------------------- #
async def stream_anthropic(
    *, base_url: str, api_key: str, model: str,
    messages: list[dict], tools: list[dict],
) -> AsyncIterator[StreamEvent]:
    """Adapt Anthropic's Messages API to our StreamEvent shape.

    Anthropic schema differences:
      - system message is a top-level `system=` param, not in messages[]
      - tool calls are content blocks of type='tool_use'
      - tool results are content blocks of type='tool_result' in user messages
      - tools schema: [{name, description, input_schema}] (not 'parameters')
    """
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed; run: pip install anthropic")

    client = AsyncAnthropic(api_key=api_key, base_url=base_url or None)

    # ---- Convert OpenAI-format messages → Anthropic format ----
    system_text = ""
    converted: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_text += (system_text and "\n\n" or "") + (m.get("content") or "")
            continue
        if role == "tool":
            # OpenAI tool_result → Anthropic user message with tool_result content block
            converted.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": m.get("content", ""),
                }],
            })
            continue
        if role == "assistant" and m.get("tool_calls"):
            # OpenAI assistant w/ tool_calls → Anthropic assistant w/ tool_use blocks
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    args_obj = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args_obj = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args_obj,
                })
            converted.append({"role": "assistant", "content": blocks})
            continue
        # Plain text message
        converted.append({"role": role, "content": m.get("content", "")})

    # ---- Convert tools schema (OpenAI → Anthropic) ----
    anth_tools = []
    for t in tools:
        f = t.get("function", {})
        anth_tools.append({
            "name": f.get("name", ""),
            "description": f.get("description", ""),
            "input_schema": f.get("parameters", {"type": "object", "properties": {}}),
        })

    # ---- Stream ----
    async with client.messages.stream(
        model=model,
        system=system_text,
        messages=converted,
        tools=anth_tools,
        max_tokens=8192,
    ) as stream:
        tool_index = 0
        async for event in stream:
            et = event.type
            if et == "content_block_start":
                b = event.content_block
                if b.type == "tool_use":
                    yield StreamEvent(
                        kind="tool_call_start",
                        tool_index=tool_index,
                        tool_id=b.id,
                        tool_name=b.name,
                    )
                    tool_index += 1
            elif et == "content_block_delta":
                d = event.delta
                if d.type == "text_delta":
                    yield StreamEvent(kind="delta", text=d.text)
                elif d.type == "input_json_delta":
                    yield StreamEvent(
                        kind="tool_call_delta",
                        tool_index=tool_index - 1,
                        tool_args_delta=d.partial_json,
                    )
        # Stream ended; get final message
        final = await stream.get_final_message()
        yield StreamEvent(kind="done", finish_reason=final.stop_reason or "end_turn")


# --------------------------------------------------------------------------- #
# Google Gemini native streamer
# --------------------------------------------------------------------------- #
async def stream_gemini(
    *, base_url: str, api_key: str, model: str,
    messages: list[dict], tools: list[dict],
) -> AsyncIterator[StreamEvent]:
    """Adapt Google's Generative Language API to our StreamEvent shape."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai package not installed; run: pip install google-genai")

    client = genai.Client(api_key=api_key)

    # Convert OpenAI messages → Gemini "contents"
    system_text = ""
    contents: list[types.Content] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_text += (system_text and "\n\n" or "") + (m.get("content") or "")
            continue
        if role == "tool":
            # Gemini functionResponse part
            contents.append(types.Content(
                role="user",
                parts=[types.Part(function_response=types.FunctionResponse(
                    name=m.get("tool_call_id", "tool"),
                    response={"result": m.get("content", "")},
                ))],
            ))
            continue
        if role == "assistant" and m.get("tool_calls"):
            parts = []
            if m.get("content"):
                parts.append(types.Part(text=m["content"]))
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    args_obj = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args_obj = {}
                parts.append(types.Part(function_call=types.FunctionCall(
                    name=fn.get("name", ""),
                    args=args_obj,
                    id=tc.get("id", ""),
                )))
            contents.append(types.Content(role="model", parts=parts))
            continue
        gem_role = "user" if role == "user" else "model"
        contents.append(types.Content(role=gem_role, parts=[types.Part(text=m.get("content", ""))]))

    # Convert tools
    gem_tools = [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=t["function"]["name"],
            description=t["function"].get("description", ""),
            parameters=t["function"].get("parameters", {"type": "object", "properties": {}}),
        ) for t in tools
    ])]

    cfg = types.GenerateContentConfig(
        tools=gem_tools,
        system_instruction=system_text or None,
    )

    tool_index = 0
    async for chunk in client.aio.models.generate_content_stream(
        model=model, contents=contents, config=cfg,
    ):
        if not chunk.candidates:
            continue
        for part in chunk.candidates[0].content.parts:
            if part.text:
                yield StreamEvent(kind="delta", text=part.text)
            if part.function_call:
                yield StreamEvent(
                    kind="tool_call_start",
                    tool_index=tool_index,
                    tool_id=part.function_call.id or f"call_{tool_index}",
                    tool_name=part.function_call.name,
                )
                # Gemini sends args as a complete dict, not streamed
                yield StreamEvent(
                    kind="tool_call_delta",
                    tool_index=tool_index,
                    tool_args_delta=json.dumps(part.function_call.args or {}),
                )
                tool_index += 1
    yield StreamEvent(kind="done", finish_reason="stop")


# --------------------------------------------------------------------------- #
# Unified entrypoint
# --------------------------------------------------------------------------- #
async def stream_chat(
    *, base_url: str, api_key: str, model: str,
    messages: list[dict], tools: list[dict],
) -> AsyncIterator[StreamEvent]:
    """Stream a chat completion from any supported provider."""
    provider = detect_provider(base_url)
    if provider == "anthropic":
        async for evt in stream_anthropic(base_url=base_url, api_key=api_key, model=model,
                                          messages=messages, tools=tools):
            yield evt
    elif provider == "gemini":
        async for evt in stream_gemini(base_url=base_url, api_key=api_key, model=model,
                                       messages=messages, tools=tools):
            yield evt
    else:
        async for evt in stream_openai(base_url=base_url, api_key=api_key, model=model,
                                       messages=messages, tools=tools):
            yield evt
