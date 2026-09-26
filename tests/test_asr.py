import json
import os
import tempfile
import unittest
from unittest import mock

from wechatauto.asr import OpenAICompatibleASR


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class ASRTests(unittest.TestCase):
    def test_base_url_and_environment_defaults(self):
        with mock.patch.dict(os.environ, {
            "WECHAT_ASR_BASE_URL": "http://asr.test",
            "WECHAT_ASR_API_KEY": "secret",
            "WECHAT_ASR_MODEL": "model-a",
        }, clear=False):
            client = OpenAICompatibleASR()
        self.assertEqual(client.base_url, "http://asr.test/v1")
        self.assertEqual(client.model, "model-a")

    def test_transcribe_file_posts_openai_multipart_and_returns_text(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF-test-audio")
            path = f.name
        try:
            client = OpenAICompatibleASR(
                "http://asr.test/v1", api_key="secret", model="model-a")
            with mock.patch("wechatauto.asr.request.urlopen",
                            return_value=_Response({"text": "测试语音"})) as call:
                self.assertEqual(client.transcribe_file(path), "测试语音")
            req = call.call_args.args[0]
            body = req.data
            self.assertIn(b'name="model"', body)
            self.assertIn(b"model-a", body)
            self.assertIn(b"RIFF-test-audio", body)
            self.assertEqual(req.full_url, "http://asr.test/v1/audio/transcriptions")
            self.assertEqual(req.get_header("Authorization"), "Bearer secret")
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
