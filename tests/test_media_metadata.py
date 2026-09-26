import unittest

from wechatauto.media import MediaDownloader


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


class MediaMetadataTests(unittest.TestCase):
    def test_local_type_code_unwraps_wechat_resource_flags(self):
        self.assertEqual(MediaDownloader._local_type_code({"local_type": 25769803825}), 49)
        self.assertEqual(MediaDownloader._local_type_code({"local_type": 3}), 3)
        self.assertIsNone(MediaDownloader._local_type_code({"local_type": None}))

    def test_protobuf_text_values_extracts_wrapped_file_names(self):
        filename = b"provider-development-release-guide.md"
        nested = b"\x0a" + _varint(len(filename)) + filename
        nested += b"\x12" + _varint(len(filename)) + filename
        packed_info = b"\x0a" + _varint(len(nested)) + nested

        self.assertEqual(
            MediaDownloader._protobuf_text_values(packed_info),
            [filename.decode(), filename.decode()],
        )
