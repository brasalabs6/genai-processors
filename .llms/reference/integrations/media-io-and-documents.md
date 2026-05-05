# Media IO And Documents

All media and document processors exchange `ProcessorPart`s. Use MIME types to
route parts and substreams to isolate realtime input, status, debug, and UI
traffic.

## Source References

- Media content contract: `genai_processors/content_api.py:39-1226`
- Audio processors: `genai_processors/core/audio.py:28-110`,
  `genai_processors/core/audio_io.py:35-146`,
  `genai_processors/core/speech_to_text.py:73-420`,
  `genai_processors/core/text_to_speech.py:41-140`,
  `genai_processors/core/vad.py:77-180`,
  `genai_processors/core/rate_limit_audio.py:37-120`
- Video and event processors: `genai_processors/core/video.py:37-220`,
  `genai_processors/core/event_detection.py:49-220`
- Document and fetch processors: `genai_processors/core/pdf.py:41-135`,
  `genai_processors/core/web.py:57-104`,
  `genai_processors/core/github.py:31-120`,
  `genai_processors/core/drive.py:181-419`,
  `genai_processors/core/filesystem.py:29-80`
- Media tests: `genai_processors/tests/audio_test.py`,
  `genai_processors/tests/video_test.py`, `genai_processors/tests/pdf_test.py`,
  `genai_processors/tests/web_test.py`, `genai_processors/tests/drive_test.py`

## ProcessorPart Media Contract

- `ProcessorPart(bytes, mimetype=...)` requires an explicit MIME type.
- Text bytes are decoded to text when the MIME type is text-like; other bytes
  become inline data.
- `ProcessorPart(PIL.Image.Image)` serializes the image into inline bytes and
  infers or validates an `image/*` MIME type.
- `ProcessorPart.from_uri(...)` creates URI/file data parts.
- `ProcessorPart.file` reconstructs a GenAI `File` when metadata `is_file` is
  set.
- Accessors include `.bytes`, `.text`, `.pil_image`, `.get_dataclass(...)`,
  `.function_call`, `.function_response`, `.to_dict()`, and `.from_dict()`.

## Audio

- `audio_io.PyAudioIn` is a source that captures microphone chunks and yields
  `audio/l16;rate=...`, `audio/l24;rate=...`, or `audio/pcm;rate=...` parts on
  substream `realtime` by default.
- `audio_io.PyAudioOut` plays audio parts with PyAudio and passes through
  non-audio parts. Set `passthrough_audio=True` to keep audio in the output
  stream.
- `audio.AudioToWav` concatenates consecutive `audio/l16` or `audio/pcm` parts
  and emits one `audio/wav` part. It flushes when a non-audio part arrives, the
  MIME type changes, or the stream ends.
- `rate_limit_audio.RateLimitAudio` splits or paces audio chunks to natural
  playback speed for streaming TTS and interruption-friendly output.

## Video

- `video.VideoIn` is a source for camera or screen frames. It yields JPEG image
  parts on substream `realtime` by default.
- `video.VideoExtract` matches video MIME types and expands a video file into
  image frames, audio, or both interleaved, depending on `VideoAVFormat`.
- Extracted frames are JPEG image parts with `metadata["video_timestamp"]`.
- Extracted audio is `audio/l16;rate=16000;channels=1`; in interleaved mode
  audio chunks follow frame timing.
- For native-video models, sending the whole video may be preferable. Use
  `VideoExtract` when a downstream processor needs frames, windows, tests, or a
  model without native video support.

## PDF

`pdf.PDFExtract` is a `PartProcessor` that matches `application/pdf`.

- It parses PDF bytes with pypdfium2 under a process lock because PDFium is not
  thread-safe.
- It emits a `status` part summarizing parsed page count and image-page count.
- It emits text delimiters and page text.
- Pages containing images/forms/paths are also rendered as PNG image parts.
- Input metadata `original_file_name` is used in status text when present.

## Google Drive Documents

`drive.Docs`, `drive.Sheets`, and `drive.Slides` are request-driven
`PartProcessor`s. Requests are dataclass JSON parts:
`DocsRequest`, `SheetsRequest`, and `SlidesRequest`.

- `Docs` exports a Google Doc as `application/pdf`.
- `Sheets` fetches grid data and emits CSV text parts for selected ranges or
  worksheets.
- `Slides` exports the deck as PDF, splits selected slides, and emits one PDF
  part per slide.
- Credentials may be passed in constructors; otherwise Google client defaults
  are used.
- Chain `PDFExtract` after Docs/Slides when you need local extraction; many
  Gemini models can consume PDF bytes directly through `GenaiModel`.

## Files And URLs

- `filesystem.GlobSource` yields files matching a glob in natural filename
  order. With `inline_file_data=True`, file bytes are loaded into parts with
  guessed MIME type and `metadata["original_file_name"]`. With
  `inline_file_data=False`, it yields file-data parts pointing at the path.
- `text.UrlExtractor` converts URLs in text into `FetchRequest` dataclass
  parts.
- `web.UrlFetch` matches `FetchRequest`, fetches the URL with httpx, yields a
  header text part, then yields fetched HTML as `text/html`. It is decorated
  with `yield_exceptions_as_parts`, so HTTP failures become status exception
  parts.
- `text.HtmlCleaner` converts HTML parts into cleaned HTML or plain text.
