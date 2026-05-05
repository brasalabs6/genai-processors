# Processors And Composition

There are two processing contracts. `Processor` transforms a stream. `PartProcessor` transforms one part and can be lifted to a stream processor for concurrent execution across the input stream.

## Source References

- `genai_processors/processor.py:135-147` defines the `ProcessorFn` protocol: `ProcessorStream -> AsyncIterable[ProcessorPartTypes]`.
- `genai_processors/processor.py:149-324` defines `Processor`, its invocation wrapper, `call`, `key_prefix`, `trace_name`, `to_processor`, and `+`.
- `genai_processors/processor.py:327-369` defines part-processor protocols and `match`.
- `genai_processors/processor.py:372-508` defines `PartProcessor`, pass-through on failed match, `+`, `//`, and lifting through `to_processor`.
- `genai_processors/processor.py:560-608` provides `@processor_function` and `@part_processor_function`.
- `genai_processors/processor.py:611-667` defines `chain`, `parallel`, and `parallel_concat`.
- `genai_processors/processor.py:780-846` implements fused part-processor chains.
- `genai_processors/processor.py:898-970` fuses adjacent `PartProcessor`s inside processor chains.
- `genai_processors/processor.py:1124-1187` implements stream-level parallel concatenation.
- `genai_processors/processor.py:1189-1343` implements part-level parallel composition and passthrough sentinels.
- `genai_processors/map_processor.py:98-194` exposes map/chain/parallel part-function combinators.
- `genai_processors/map_processor.py:259-383` implements eager concurrent chain and parallel execution.

## Operators

- `p + q`: sequential composition.
- `part_p + part_q`: fused part chain; each matching part can fan out through the chain.
- `part_p + stream_p`: mixed chain; part processor is lifted to stream processor.
- `part_p // part_q`: part-level parallel composition; both processors see the same input part when their match functions pass.
- `parallel_concat([p, q])`: stream-level parallel fan-out; outputs are concatenated/merged by processor branch.
- `PASSTHROUGH_FALLBACK`: in `//`, yield the input only when no branch outputs anything.
- `PASSTHROUGH_ALWAYS`: in `//`, always include the input part as an output.

## Match Contract

`match(part)` is a scheduling and pass-through hint. A `PartProcessor` whose match returns false must behave as pass-through. The wrapper enforces pass-through before `call()` for normal invocation; wrappers and map functions also use `match` to skip task creation.

In parallel composition, no matching processor usually means drop. Add `PASSTHROUGH_FALLBACK` to preserve unmatched inputs, or `PASSTHROUGH_ALWAYS` to preserve every input.

## Invariants

- Decorated processor functions must be async generator functions.
- `Processor` implementations consume streams; `PartProcessor` implementations consume one `ProcessorPart`.
- Adjacent `PartProcessor`s are fused to maximize concurrency.
- Part-function chains preserve left-to-right output order within the tree while eagerly scheduling deeper work.
- Part-level parallel output is emitted in processor-list order, not completion order.
- Stream-level switch/parallel branches may reorder output across branches.
- `key_prefix` should change when constructor arguments change output; otherwise cache keys and traces can collide.

## Read Next

- `.llms/reference/architecture/runtime-flow.md`
- `.llms/reference/architecture/async-context-and-taskgroups.md`
- `.llms/reference/concepts/substreams-and-routing.md`
