import sys
import unittest
from pathlib import Path
import tempfile
import numpy as np

from pose_backends import decode_pose, letterbox
from app_paths import resource_path


class BackendContractTests(unittest.TestCase):
    def test_letterbox_square_tensor_and_coordinates(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        tensor, ratio, pad = letterbox(image)
        self.assertEqual(tensor.shape, (1, 3, 640, 640))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertEqual(ratio, .5)
        self.assertEqual(pad, (0, 140))

    def test_end_to_end_pose_output_and_no_detection(self):
        rows = np.zeros((1, 300, 57), np.float32)
        rows[0, 0, :6] = [50, 150, 250, 350, .9, 0]
        rows[0, 0, 6:] = np.tile([100, 200, .8], 17)
        result = decode_pose(rows, (720, 1280, 3), .5, (0, 140))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].points.shape, (17, 2))
        np.testing.assert_allclose(result[0].points[0], [200, 120])
        np.testing.assert_allclose(result[0].box, [100,20,500,420])
        self.assertEqual(decode_pose(np.zeros_like(rows), (720,1280,3), .5, (0,140)), [])

    def test_invalid_output_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            decode_pose(np.zeros((1, 3, 10), np.float32), (720,1280,3), .5, (0,140))

    def test_nonfinite_people_are_filtered(self):
        rows = np.zeros((1, 1, 57), np.float32)
        rows[0,0,4] = .9
        rows[0,0,6:] = np.tile([100,200,.9],17)
        rows[0,0,6] = np.nan
        self.assertEqual(decode_pose(rows, (720,1280,3), .5, (0,140)), [])

    def test_importing_backends_does_not_import_training_frameworks(self):
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('ultralytics', sys.modules)
