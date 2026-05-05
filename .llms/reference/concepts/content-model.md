# Content Model

The content model separates the single unit (`ProcessorPart`) from collections/streams (`ProcessorContent`, `ContentStream`). Preserve parts as long as possible; reduce to text, images, GenAI content, or dataclasses only at boundaries.

## Source References

- `genai_processors/content_api.py:39-68` defines `ProcessorPart` constructor fields.
- `genai_processors/content_api.py:91-153` shows supported construction inputs and metadata inheritance.
- `genai_processors/content_api.py:155-177` derives MIME type from explicit args, inline data, function calls/responses, or text.
- `genai_processors/content_api.py:228-310` exposes role, bytes, substream, MIME, text, and metadata accessors.
- `genai_processors/content_api.py:392-572` provides constructors for URI, function call/response, code execution, bytes, proto, tool cancellation, dataclass, and end-of-turn.
- `genai_processors/content_api.py:575-672` serializes, deserializes, and copies `ProcessorPart`.
- `genai_processors/content_api.py:695-820` defines `ContentStream` as an async adapter with reducers.
- `genai_processors/content_api.py:841-980` defines `ProcessorContent` as a static multi-part container.
- `genai_processors/content_api.py:994-1012` defines accepted `ProcessorPartTypes` and `ProcessorContentTypes`.
- `genai_processors/content_api.py:1065-1252` reduces or converts content to text/images/videos/GenAI values.

## Contracts

`ProcessorPart` wraps a GenAI SDK `Part` plus metadata:

- `role`: producer or conversation role; usually empty, `user`, or `model`.
- `substream_name`: logical lane; empty string means default stream.
- `mimetype`: semantic type used for dispatch and access safety.
- `metadata`: arbitrary auxiliary data; copied by `copy()` and serialized by `to_dict()`.

`ProcessorContent` is a static container. It can be built from parts, strings, bytes with MIME type, images, GenAI files, GenAI content, and iterables. Iterating yields `ProcessorPart`.

`ContentStream` is an async adapter. A stream backed by a generator may be single-use; static content streams can be iterated multiple times.

## Invariants

- Bytes require a MIME type when constructing a `ProcessorPart`.
- `part.text` raises for non-text MIME types; check MIME or let the error signal misuse.
- Empty substream name is the default content stream, not missing data.
- Copy before mutating metadata or part fields if aliases might share the same `ProcessorPart`.
- `ProcessorPart.from_dict(part.to_dict())` is the JSON-compatible round trip.
- `as_text(..., substream_name=...)` filters by exact substream name, not prefix.
- `to_genai_contents()` groups consecutive parts by role and file-ness.

## Read Next

- `.llms/reference/concepts/processors-and-composition.md`
- `.llms/reference/concepts/substreams-and-routing.md`
- `.llms/reference/architecture/runtime-flow.md`
