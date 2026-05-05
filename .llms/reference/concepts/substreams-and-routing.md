# Substreams And Routing

Substreams are metadata on `ProcessorPart`, not separate stream objects. They let one physical stream carry default content plus out-of-band lanes such as status, debug, UI, realtime audio, or named routing channels.

## Source References

- `genai_processors/content_api.py:76-81` documents substream construction and inheritance.
- `genai_processors/content_api.py:259-268` exposes `substream_name`.
- `genai_processors/content_api.py:1037-1041` provides `get_substream_name` for routing.
- `genai_processors/context.py:29-53` defines `prompt`, `debug`, `status`, `ui`, and the default reserved-substream set.
- `genai_processors/context.py:130-147` exposes reserved-substream lookup and prefix matching.
- `genai_processors/processor.py:510-517` builds `debug()` and `status()` parts.
- `genai_processors/processor.py:973-984` captures reserved stream parts from processor chains.
- `genai_processors/processor.py:996-1034` captures reserved parts between stream processors and yields them through the output queue.
- `genai_processors/processor.py:1037-1070` captures reserved parts before and after part-processor calls.
- `genai_processors/processor.py:1073-1118` applies reserved capture inside part-processor chains.
- `genai_processors/processor.py:1258-1315` applies reserved capture inside part-level parallel composition.
- `genai_processors/switch.py:34-142` routes streams by first matching case; `genai_processors/switch.py:145-227` routes individual parts by first matching case.
- `genai_processors/tests/processor_test.py:878-907` and `genai_processors/tests/processor_test.py:1267-1296` assert custom reserved substreams bypass chain/parallel processors.
- `genai_processors/tests/processor_test.py:1228-1265` asserts reserved `status`/`debug` outputs are yielded promptly.
- `genai_processors/tests/switch_test.py:39-82` asserts stream switch routing and cross-case ordering behavior.

## Reserved Substreams

Default reserved prefixes are:

- `debug`
- `status`
- `ui`

Reserved parts are captured and yielded immediately instead of being passed to the next processor in a chain or branch. Matching is prefix-based, so `status.progress` is reserved when `status` is reserved.

Custom context can replace the reserved set:

```python
async with processor.context(reserved_substreams=["custom_debug"]):
  async for part in chain(content):
    ...
```

## Switch Routing

`Switch(match_fn).case(value_or_predicate, processor).default(processor)` routes each input part to the first matching stream processor. Each case owns an input queue, cases run concurrently, and outputs are merged. Ordering is guaranteed only within one case processor, not across cases.

`PartSwitch` does the same first-match routing for one part at a time and is preferred when all cases are `PartProcessor`s.

Common routing keys:

- `content_api.get_substream_name`
- `lambda part: part.mimetype`
- `content_api.as_text` only when all routed parts are text-compatible
- custom predicates over `ProcessorPart`

## Invariants

- Empty substream name is ordinary default content and is not reserved.
- Reserved substreams bypass downstream processors in chain and parallel composition.
- Custom reserved-substream context replaces defaults; include defaults explicitly if they should remain reserved.
- Do not route by `.text` unless non-text parts are impossible or intended to raise.
- `Switch` without a default drops unmatched parts.
- `PartSwitch` without a default yields nothing for unmatched parts.
- A default case must be added last; adding another case after default raises.

## Read Next

- `.llms/reference/architecture/async-context-and-taskgroups.md`
- `.llms/reference/concepts/processors-and-composition.md`
- `.llms/reference/architecture/runtime-flow.md`
