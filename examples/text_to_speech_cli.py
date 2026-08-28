# Copyright 2025 DeepMind Technologies Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
r"""Command Line Interface to test the Text-to-Speech GenAI Processor.

## Setup

To install the dependencies for this script, run:

```
pip install --upgrade google-cloud-texttospeech genai-processors
```

Before running this script, ensure the `GOOGLE_PROJECT_ID` environment
variable is set to your project_id (from Google Cloud Console).

## Run

To run the script:

```shell
python3 ./text_to_speech_cli.py
```

Enter the text you want to synthesize and press enter.
"""

import asyncio
import os
import time

from genai_processors.core import audio_io
from genai_processors.core import text
from genai_processors.core import text_to_speech
import pyaudio


# You need to define the project id in the environment variables.
# export GOOGLE_PROJECT_ID=...
GOOGLE_PROJECT_ID = os.environ['GOOGLE_PROJECT_ID']


async def run_tts() -> None:
  """Runs speech-to-text in a CLI environment."""

  pya = pyaudio.PyAudio()
  tts_processor = text_to_speech.TextToSpeech(  # pyrefly: ignore[unsupported-operation]
      project_id=GOOGLE_PROJECT_ID
  ) + audio_io.PyAudioOut(pya)

  print(
      f'{time.perf_counter()} - TTS Processor ready. Enter q to quit.\nNOTE:'
      ' finish all your input with a punctuation to indicate an end of'
      ' sentence. E.g.: "Hello, world!" or "hi."\nIMPORTANT: after 5 seconds'
      ' without activity (after the first sentence), the TTS will stop.'
  )
  print('Use ctrl+D to quit.')
  async for _ in tts_processor(text.terminal_input('message > ')):
    pass


if __name__ == '__main__':
  asyncio.run(run_tts())
