"""Run real empirical scenarios against Gemini Live pipelines."""

import argparse
import asyncio
import datetime
import os
from pathlib import Path
from typing import AsyncIterable

from genai_processors import content_api

from leonidas import capabilities
from leonidas import config
from leonidas.e2e import assets
from leonidas.e2e import generate_assets
from leonidas.e2e import manifest
from leonidas.e2e import report
from leonidas.e2e import runner
from leonidas.pipelines import registry


DEFAULT_RESULTS = Path(__file__).parents[1] / '.runtime' / 'e2e' / 'results'


async def _inputs(
    image: bytes, audio: bytes
) -> AsyncIterable[content_api.ProcessorPart]:
  yield content_api.ProcessorPart(
      image,
      mimetype='image/jpeg',
      role='user',
      substream_name='realtime',
  )
  chunk_size = 16000 * 2 // 10
  for offset in range(0, len(audio), chunk_size):
    yield content_api.ProcessorPart(
        audio[offset : offset + chunk_size],
        mimetype='audio/pcm;rate=16000',
        role='user',
        substream_name='realtime',
    )
    await asyncio.sleep(0.1)
  yield content_api.ProcessorPart(
      '',
      role='user',
      substream_name='realtime',
      metadata={'audio_stream_end': True},
  )
  # A live processor is bidirectional and must stay open while output arrives.
  await asyncio.Event().wait()


async def run_models(
    *,
    api_key: str,
    models: tuple[str, ...],
    scenarios: tuple[manifest.Scenario, ...],
    asset_root: Path,
) -> list[runner.EmpiricalResult]:
  pipelines = registry.PipelineRegistry(api_key)
  results = []
  for scenario in scenarios:
    audio_path = asset_root / f'{scenario.id}.wav'
    image_path = asset_root / f'{scenario.id}.png'
    audio = assets.audio_as_pcm16_16khz(audio_path)
    image = assets.image_as_jpeg(image_path)
    for model_id in models:
      agent_config = config.AgentConfig.default().with_updates(
          {
              'model_id': model_id,
              'chattiness': 0,
              'objective': (
                  'Responda em português ao pedido do usuário usando a imagem '
                  'e confirme de forma breve o que ouviu.'
              ),
          }
      )
      result = await runner.run_processor(
          pipelines.create(agent_config),
          _inputs(image, audio),
          model_id=model_id,
          scenario_id=scenario.id,
          expected_terms=scenario.expected_terms,
          timeout_seconds=scenario.timeout_seconds,
          minimum_audio_seconds=scenario.minimum_audio_seconds,
      )
      results.append(result)
  return results


async def _main(args: argparse.Namespace) -> int:
  api_key = os.environ.get('GOOGLE_API_KEY')
  if not api_key:
    print('BLOCKED_EXTERNAL: GOOGLE_API_KEY is not set')
    return 2
  scenarios = manifest.load(args.manifest)
  models = (
      (capabilities.MODEL_LIVE_2_5, capabilities.MODEL_LIVE_3_1)
      if args.models == 'all'
      else (args.models,)
  )
  for scenario in scenarios:
    assets.validate_audio(args.assets / f'{scenario.id}.wav')
    assets.validate_image(args.assets / f'{scenario.id}.png')
  results = await run_models(
      api_key=api_key,
      models=models,
      scenarios=scenarios,
      asset_root=args.assets,
  )
  run_id = datetime.datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
  json_path, markdown_path = report.write(args.results, results, run_id=run_id)
  for result in results:
    print(
        f'model={result.model_id} scenario={result.scenario_id} '
        f'passed={result.passed} audio_seconds={result.audio_seconds:.2f} '
        f'ttfa_ms={result.ttfa_ms} error={result.error_code}'
    )
  print(f'report_json={json_path} report_markdown={markdown_path}')
  return 0 if all(result.passed for result in results) else 1


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--manifest',
      type=Path,
      default=Path(__file__).with_name('scenarios.json'),
  )
  parser.add_argument(
      '--assets', type=Path, default=generate_assets.DEFAULT_ASSET_ROOT
  )
  parser.add_argument('--results', type=Path, default=DEFAULT_RESULTS)
  parser.add_argument('--models', default='all')
  return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == '__main__':
  raise SystemExit(main())
