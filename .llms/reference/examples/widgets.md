# Dynamic Widgets

## Source References

- `examples/widgets/widgets.py`
- `examples/widgets/widgets_ais.py`
- `examples/widgets/ais_app/index.tsx`
- `examples/widgets/README.md`
- `genai_processors/core/function_calling.py`
- `genai_processors/core/realtime.py`
- `genai_processors/dev/live_server.py`

## Entrypoint

- Server: from `examples/widgets`, run
  `python3 widgets_ais.py --alsologtostderr`.
- AI Studio applet source: `examples/widgets/ais_app/`.
- Factory: `widgets.create_dr_widget(api_key)`.

## Pipeline / Data Flow

- `create_dr_widget` creates `ImageGenerator` and `PlotGenerator` tool objects.
- Root `GenaiModel` is configured with automatic function calling disabled and
  tool declarations for both async tool methods.
- `function_calling.FunctionCalling(model=realtime.LiveProcessor(...), fns=...,
  is_bidi_model=True)` executes tool calls while preserving bidirectional chat.
- `ImageGenerator.create_image_from_description` immediately yields a function
  response, then streams image-model output on substream `ui`.
- `PlotGenerator.create_plot_from_description` immediately yields a function
  response, then streams generated standalone HTML as inline-data inside
  function-response parts on substream `ui`.
- `widgets_ais.py` serves the processor over WebSocket with
  `live_server.run_server`.
- The TS app sends text messages and renders text, images, HTML iframes,
  function calls, and function responses.

## Dependencies / Env

- Requires `GOOGLE_API_KEY`.
- Suggested install: `genai-processors[live]`.
- Models: root/plot `gemini-3-flash-preview`; image
  `gemini-2.5-flash-image`.
- Default WebSocket port: `8765`.

## Demonstrated Processor Contracts

- Async tools can yield an early `ProcessorPart.from_function_response(...)`
  and continue producing UI-only output.
- UI-bound parts use substream `ui` in code, keeping tool rendering separate
  from the model prompt stream.
- HTML widgets are carried as inline data with MIME type `text/html`.
- Function-call ids let the client associate streamed responses with original
  tool calls.

## Gotchas

- README text mentions `status` for direct-to-client routing, but code uses
  `ui` substream for widget output.
- Plot output prompt forbids external JS and markdown fences; client expects raw
  HTML/SVG.
- Tool outputs may stream after the model has continued; UI must handle
  out-of-order widget completion.
