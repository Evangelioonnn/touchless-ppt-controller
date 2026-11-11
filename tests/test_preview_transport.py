import struct
import unittest
import numpy as np
from preview_transport import CAPACITY, HEADER, PAYLOAD_OFFSET, FramePublisher


class PreviewTransportTests(unittest.TestCase):
    def publisher(self):
        data = bytearray(CAPACITY)
        return FramePublisher('Local\\TouchlessPPTPreview.' + 'a' * 32, data), data

    def test_frame_contract_is_bounded_bgr_with_even_committed_sequence(self):
        publisher, data = self.publisher()
        image = np.arange(60, dtype=np.uint8).reshape(4, 5, 3)
        publisher.publish(image, 12.5)
        self.assertEqual(HEADER.unpack(data[:HEADER.size]), (b'TPV1', 1, 2, 5, 4, 15, 60, 12.5))
        self.assertEqual(data[PAYLOAD_OFFSET:PAYLOAD_OFFSET + 60], image.tobytes())
        publisher.publish(image, 13)
        self.assertEqual(struct.unpack('<q', data[8:16])[0], 4)
        self.assertEqual(len(data), CAPACITY)

    def test_noncontiguous_image_and_close(self):
        publisher, data = self.publisher()
        image = np.arange(60, dtype=np.uint8).reshape(4, 5, 3)[:, ::-1]
        publisher.publish(image, 1)
        self.assertEqual(data[PAYLOAD_OFFSET:PAYLOAD_OFFSET + 60], image.tobytes())
        publisher.close(); publisher.publish(image, 2)
        self.assertEqual(publisher.sequence, 2)

    def test_invalid_format_or_capacity_is_rejected_before_writing(self):
        publisher, data = self.publisher()
        for image in (np.zeros((4, 4), np.uint8), np.zeros((4, 4, 3), np.float32), np.zeros((2160, 4096, 3), np.uint8)):
            with self.assertRaises(ValueError): publisher.publish(image)
        self.assertEqual(data[:40], bytes(40))

    def test_channel_names_cannot_be_arbitrary_files_or_global_objects(self):
        for name in ('Global\\anything', 'random', 'Local\\TouchlessPPTPreview.bad', '../file'):
            with self.assertRaises(ValueError): FramePublisher(name, bytearray(CAPACITY))
