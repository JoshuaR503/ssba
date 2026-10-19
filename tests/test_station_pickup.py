"""Guard against old poses, stale camera calibration and unsafe dispatch."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_pickup_without_id4 as runner
from cube_vision import select

ROOT = Path(__file__).resolve().parents[1]


class StationPickupTests(unittest.TestCase):
    def test_contact_and_release_match_photo_records(self):
        # Independent regression values transcribed from IMG_0996/1005,
        # IMG_1012/1020 and IMG_1027/1038; no photo archive is needed to test.
        expected = {
            'deposition': ({'1': -2, '3': 74, '5': -56, '6': -4}, {'1': -24, '3': 90, '5': -54}),
            'metrology': ({'1': -2, '3': 70, '5': -60, '6': -46}, {'1': -36, '3': 90, '5': -70}),
            'etch': ({'1': 6, '3': 76, '5': -60, '6': 32}, {'1': -44, '3': 90, '5': -58}),
        }
        for name, (grip, release) in expected.items():
            steps = runner.build_steps(name)
            state={}
            for label,joints in steps:
                state.update(joints)
                if 'Grip cube' in label:
                    self.assertEqual({k:state[k] for k in (1,3,5,6)}, {int(k):grip[k] for k in ('1','3','5','6')})
                if 'Release at destination' in label:
                    self.assertEqual({k:state[k] for k in (1,3,5)}, {int(k):release[k] for k in ('1','3','5')})

    def test_execute_dispatches_all_three_once_at_500ms(self):
        sent = []
        def respond(request, timeout):
            sent.append(json.loads(request.data))
            return io.StringIO(json.dumps({'result': [True], 'id': len(sent)}))
        with patch.object(sys, 'argv', ['test_pickup_without_id4.py', '--execute']), patch.object(runner, 'urlopen', side_effect=respond), patch.object(runner.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 0)
        self.assertEqual(len(sent), 30)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.65] * 30)
        for request in sent:
            self.assertEqual(request['method'], 'SetPWMServo')
            self.assertEqual(request['params'][0], 500)
            ids = request['params'][1::2]
            self.assertTrue(set(ids) <= {1, 3, 5, 6})
            if 3 in ids:
                self.assertGreaterEqual(dict(zip(ids, request['params'][2::2]))[3], 30)

    def test_go_flag_is_step_by_step_without_execute(self):
        with patch.object(sys,'argv',['test_pickup_without_id4.py','--go']),patch.object(runner,'urlopen') as request,patch('builtins.input',return_value='q') as prompt,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(),0)
            prompt.assert_called_once()
            request.assert_not_called()

    def test_rejection_stops_without_retry_or_return(self):
        with patch.object(sys, 'argv', ['test_pickup_without_id4.py', '--execute']), patch.object(runner, 'urlopen', return_value=io.StringIO('{"result": [false]}')) as request, patch.object(runner.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 1)
            self.assertEqual(request.call_count, 1)

    def test_old_vision_config_rejected_before_camera_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zones.json'
            path.write_text('{"zones": []}')
            with patch('cube_vision.snapshot') as snapshot:
                with self.assertRaisesRegex(RuntimeError, 'older layout'):
                    select('unused', path, pose_set=runner.POSE_SET, observation_pose=runner.BASE_POSE, stations=list(runner.CUBES))
                snapshot.assert_not_called()

    def test_invalid_later_station_prevents_plan(self):
        with patch.dict(runner.CUBES['etch'], pickup={'3': 29, '5': -60, '6': 32}):
            with self.assertRaisesRegex(ValueError, 'ID3'):
                runner.build_steps()
        for duration in [0, 1000, 1500, 2000]:
            with self.assertRaises(ValueError):
                runner.payload({3: 48}, 1, duration)


if __name__ == '__main__':
    unittest.main()
