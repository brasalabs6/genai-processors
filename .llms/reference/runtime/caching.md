# Caching

Caching stores `ProcessorContent` outputs for repeated processor inputs. Use it
around expensive, deterministic work: LLM calls, metadata extraction,
document processing, embeddings, or remote fetches.

## Source References

- Cache interface: `genai_processors/cache_base.py:24-68`
- Default hashing and in-memory backend: `genai_processors/cache.py:39-137`
- SQL cache context and backend: `genai_processors/sql_cache.py:52-236`
- Cached wrappers: `genai_processors/processor.py:1522-1649`
- Cache tests: `genai_processors/tests/cache_test.py:26-160`,
  `genai_processors/tests/sql_cache_test.py:21-125`

## Cache Interface

Implement `cache_base.CacheBase` for backends. Required methods:

- `hash_fn`: callable mapping `ProcessorContentTypes` to a string key or
  `None` for uncacheable input.
- `lookup(query=None, *, key=None)`: returns `ProcessorContent` or
  `CacheMiss`.
- `put(query=None, *, key=None, value=...)`: stores a value.
- `remove(query)`: deletes by query.
- `with_key_prefix(prefix)`: returns a cache view with prefixed generated keys.

## Default Hashing

`cache.default_processor_content_hash` canonicalizes
`ProcessorContent` by serializing part dictionaries to sorted JSON and hashing
with `xxhash.xxh128`.

- Part order matters.
- `metadata["capture_time"]` is ignored.
- If any input part is an exception MIME type, hashing returns `None`, making
  the item uncacheable.
- Cache wrappers also avoid storing outputs containing `text/x-exception`
  parts.

## Built-In Backends

`cache.InMemoryCache`:

- Uses `cachetools.TTLCache`.
- Configured with `ttl_hours`, `max_items`, and optional `hash_fn`.
- `with_key_prefix` shares the underlying cache and wraps the hash function.

`sql_cache.SqlCache`:

- Persistent SQLAlchemy-backed cache, usually created with
  `sql_cache.sql_cache(db_url, ttl_hours=..., hash_fn=...)`.
- Stores serialized content in table `content_cache`.
- Supports expiring rows by `expires_at`.
- Uses an async lock around session operations.
- Best for long-running agents and development retries; avoid very large parts
  such as raw video frames.

## Wrappers

`processor.CachedPartProcessor` wraps a `PartProcessor`.

- Caches each matching input part independently.
- Preserves per-part streaming and output order.
- On miss, yields wrapped output as it arrives, records parts, and stores the
  result asynchronously after success.

`processor.CachedProcessor` wraps a `Processor`.

- Buffers the entire input stream before lookup.
- Use only when whole-stream input is required or input streaming is not needed.
- On miss, yields wrapped output as it arrives, records parts, and stores the
  result asynchronously after success.

Both wrappers use the same context variable. Set the active cache with either
`CachedProcessor.set_cache(cache)` or `CachedPartProcessor.set_cache(cache)`.
Pass `default_cache` to the wrapper for a fallback when no context cache is set.

## Key Prefixes

Each wrapper prefixes cache keys with `key_prefix` or the wrapped processor's
`key_prefix`. Update this prefix when processor behavior changes. Provider
wrappers should include model names or behavior-changing options in their
`key_prefix` when necessary to avoid stale cross-model results.
