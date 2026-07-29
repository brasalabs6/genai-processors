import asyncio
import unittest

from examples.live_commentator import commentator
from genai_processors import content_api
from genai_processors.core import live_model
from google.genai import types as genai_types


class CommentatorModelProfileTest(unittest.TestCase):

  def test_default_profile_preserves_gemini_2_5_behavior(self):
    profile = commentator.resolve_live_model_profile(commentator.MODEL_LIVE)

    self.assertEqual(
        profile.model_name,
        'gemini-2.5-flash-native-audio-preview-12-2025',
    )
    self.assertEqual(
        profile.default_input_transport,
        live_model.DefaultInputTransport.CLIENT_CONTENT,
    )
    self.assertEqual(
        profile.function_call_mode,
        commentator.FunctionCallMode.ASYNC_SCHEDULED,
    )
    declarations = [
        declaration
        for tool in commentator.create_live_tools(profile)
        for declaration in tool.function_declarations
    ]
    self.assertEqual(
        [declaration.name for declaration in declarations],
        ['start_commentating', 'wait_for_user'],
    )
    self.assertTrue(
        all(
            declaration.behavior == 'NON_BLOCKING'
            for declaration in declarations
        )
    )

  def test_gemini_3_1_profile_uses_realtime_synchronous_control(self):
    profile = commentator.resolve_live_model_profile(commentator.MODEL_LIVE_3_1)

    self.assertEqual(
        profile.default_input_transport,
        live_model.DefaultInputTransport.REALTIME_INPUT,
    )
    self.assertEqual(
        profile.function_call_mode,
        commentator.FunctionCallMode.SYNCHRONOUS,
    )
    declarations = [
        declaration
        for tool in commentator.create_live_tools(profile)
        for declaration in tool.function_declarations
    ]
    self.assertEqual(
        [declaration.name for declaration in declarations],
        ['start_commentating', 'wait_for_user', 'stop_commentating'],
    )
    self.assertTrue(
        all(declaration.behavior is None for declaration in declarations)
    )

  def test_unknown_live_model_is_rejected(self):
    with self.assertRaisesRegex(ValueError, 'Unsupported live model'):
      commentator.resolve_live_model_profile('gemini-unknown-live')


class LiveCommentatorControlTest(unittest.TestCase):

  def test_synchronous_comment_uses_realtime_text(self):
    input_queue: asyncio.Queue[content_api.ProcessorPart] = asyncio.Queue()
    processor = commentator.LiveCommentator(
        live_api_processor=unittest.mock.Mock(),
        function_call_mode=commentator.FunctionCallMode.SYNCHRONOUS,
    )

    processor._commentator.update(commentator.Action.TURN_ON)
    processor._start_commentating(input_queue, message='next comment')

    part = input_queue.get_nowait()
    self.assertEqual(part.text, 'next comment')
    self.assertEqual(part.substream_name, 'realtime')
    self.assertIsNone(part.part.function_response)

  def test_synchronous_function_response_has_no_async_scheduling(self):
    input_queue: asyncio.Queue[content_api.ProcessorPart] = asyncio.Queue()
    processor = commentator.LiveCommentator(
        live_api_processor=unittest.mock.Mock(),
        function_call_mode=commentator.FunctionCallMode.SYNCHRONOUS,
    )

    processor._respond_to_wait_for_user(input_queue, 'call-id')

    response = input_queue.get_nowait().part.function_response
    self.assertEqual(response.id, 'call-id')
    self.assertEqual(response.name, 'wait_for_user')
    self.assertIsNone(response.scheduling)
    self.assertIsNone(response.will_continue)

  def test_async_profile_preserves_scheduled_function_response(self):
    input_queue: asyncio.Queue[content_api.ProcessorPart] = asyncio.Queue()
    processor = commentator.LiveCommentator(
        live_api_processor=unittest.mock.Mock(),
        function_call_mode=commentator.FunctionCallMode.ASYNC_SCHEDULED,
    )
    processor._commentator.update(commentator.Action.TURN_ON, 'call-id')

    processor._start_commentating(input_queue, message='next comment')

    response = input_queue.get_nowait().part.function_response
    self.assertEqual(response.id, 'call-id')
    self.assertEqual(response.name, 'start_commentating')
    self.assertEqual(
        response.scheduling,
        genai_types.FunctionResponseScheduling.WHEN_IDLE,
    )


if __name__ == '__main__':
  unittest.main()
