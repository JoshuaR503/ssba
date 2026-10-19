"""Offline checks: mock all provider requests; never contact robot or provider."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import supervisor as s


class SupervisorTests(unittest.TestCase):
    def state(self):
        return {'pending': list(s.STATIONS), 'available': dict.fromkeys(s.STATIONS, True), 'tray_ready': True, 'arm_idle': True}

    def test_demo_no_network(self):
        with patch.object(s, 'urlopen') as request:
            self.assertEqual(s.demo()['example_grip_check']['suggested_action'], 'pause')
            request.assert_not_called()

    def test_blocked_station_rejected(self):
        state = self.state(); state['available']['metrology'] = False
        with self.assertRaises(ValueError):
            s.validate_plan({'action': 'pick_station', 'station': 'metrology', 'reason': 'try'}, state)

    def test_busy_arm_or_unready_tray_blocks(self):
        for flag in ('arm_idle', 'tray_ready'):
            state = self.state(); state[flag] = False
            with patch.object(s, 'ask_gemini') as ask:
                self.assertEqual(s.plan(state, 'collect')[0]['action'], 'pause')
                ask.assert_not_called()

    def test_unknown_action_or_angle_payload_rejected(self):
        for decision in ({'action': 'set_servo', 'station': '', 'reason': 'move'},
                         {'action': 'pick_station', 'station': 'etch', 'reason': 'ok', 'angles': {'4': 10}},
                         {'action': 'done', 'station': '', 'reason': 'skip'}):
            with self.assertRaises(ValueError):
                s.validate_plan(decision, self.state())

    def test_complete_without_api(self):
        state = self.state(); state['pending'] = []
        with patch.object(s, 'ask_gemini') as ask:
            self.assertEqual(s.plan(state, 'collect')[0]['action'], 'done')
            ask.assert_not_called()

    def test_holding_requires_both_evidence_flags(self):
        for between, clear in [(False, False), (True, False), (False, True)]:
            result = s.validate_grip({'status': 'held', 'cube_visible_between_fingers': between, 'cube_clear_of_surface': clear, 'evidence': 'view'})
            self.assertEqual(result['status'], 'uncertain')
            self.assertEqual(result['suggested_action'], 'pause')
        result = s.validate_grip({'status': 'held', 'cube_visible_between_fingers': True, 'cube_clear_of_surface': True, 'evidence': 'cube visibly held and suspended'})
        self.assertEqual(result['suggested_action'], 'continue')

    def test_empty_and_uncertain_pause(self):
        for status in ('empty', 'uncertain'):
            self.assertEqual(s.validate_grip({'status': status, 'cube_visible_between_fingers': False, 'cube_clear_of_surface': False, 'evidence': 'not visibly held'})['suggested_action'], 'pause')
        with self.assertRaises(ValueError):
            s.validate_grip({'status': 'held', 'cube_visible_between_fingers': 'true', 'cube_clear_of_surface': True, 'evidence': 'view'})

    def test_real_http_request_contract_mocked(self):
        answer = {'action': 'pick_station', 'station': 'etch', 'reason': 'requested first'}
        raw = json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(answer)}]}}]}).encode()
        with patch.dict(s.os.environ, {'GEMINI_API_KEY': 'test-only-key'}), patch.object(s, 'urlopen', return_value=io.BytesIO(raw)) as request:
            result, elapsed = s.plan(self.state(), 'Collect red first')
            self.assertEqual(result, answer)
            self.assertGreaterEqual(elapsed, 0)
            req = request.call_args.args[0]
            self.assertEqual(req.full_url, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent')
            body = json.loads(req.data)
            self.assertEqual(body['generationConfig']['responseJsonSchema'], s.PLAN_SCHEMA)
            self.assertNotIn('tools', body)

    def test_missing_key_or_partial_answer_rejected(self):
        with patch.object(s, 'local_api_key', return_value=''), patch.object(s, 'urlopen') as request:
            with self.assertRaises(ValueError):
                s.ask_gemini('x', s.PLAN_SCHEMA)
            request.assert_not_called()
        raw = json.dumps({'candidates': [{'finishReason': 'MAX_TOKENS'}]}).encode()
        with patch.dict(s.os.environ, {'GEMINI_API_KEY': 'test-only-key'}), patch.object(s, 'urlopen', return_value=io.BytesIO(raw)):
            with self.assertRaises(ValueError):
                s.ask_gemini('x', s.PLAN_SCHEMA)

    def test_bad_state_rejected(self):
        for pending in (['unknown'], ['etch', 'etch'], [None]):
            state = self.state(); state['pending'] = pending
            with self.assertRaises(ValueError):
                s.validate_state(state)
        state = self.state(); state['tray_ready'] = 'true'
        with self.assertRaises(ValueError):
            s.validate_state(state)

    def test_before_after_image_order(self):
        result = {'status': 'uncertain', 'cube_visible_between_fingers': False, 'cube_clear_of_surface': False, 'evidence': 'obscured'}
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder)/'before.jpg', Path(folder)/'after.jpg'
            before.write_bytes(b'\xff\xd8\xffbefore'); after.write_bytes(b'\xff\xd8\xffafter')
            with patch.object(s, 'ask_gemini', return_value=(result, 0.1)) as ask:
                assessment, _ = s.check_grip(before, after, 'etch')
                self.assertEqual(assessment['suggested_action'], 'pause')
                self.assertEqual(ask.call_args.args[2], [s.image_part(before), s.image_part(after)])
            before.write_bytes(b'HEIC')
            with self.assertRaises(ValueError):
                s.image_part(before)


    def test_camera_only_reads_snapshot_and_validates_inventory(self):
        inventory = {'red': 'present', 'green': 'uncertain', 'blue': 'absent', 'pickup_area_visible': True, 'evidence': 'Red cube visible; green region occluded; blue area clear.'}
        with patch.object(s, 'urlopen', return_value=io.BytesIO(b'\xff\xd8\xffframe')) as request, patch.object(s, 'ask_gemini', return_value=(inventory, 0.2)) as ask:
            result, elapsed = s.inspect_camera('raspberrypi.local', api_key='test-only-key')
            self.assertEqual(result, inventory)
            self.assertEqual(elapsed, 0.2)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0], 'http://raspberrypi.local:8080/?action=snapshot')
            self.assertEqual(ask.call_args.kwargs['api_key'], 'test-only-key')
            self.assertEqual(ask.call_args.args[1], s.PRESENCE_SCHEMA)

    def test_camera_failure_does_not_call_provider(self):
        with patch.object(s, 'urlopen', side_effect=OSError('unreachable')), patch.object(s, 'ask_gemini') as ask:
            with self.assertRaises(OSError):
                s.inspect_camera()
            ask.assert_not_called()

    def test_inventory_cannot_be_used_as_motion_or_readiness(self):
        for result in ({'red': 'present', 'green': 'present', 'blue': 'present', 'evidence': 'visible', 'move': True},
                       {'red': 'maybe', 'green': 'present', 'blue': 'present', 'evidence': 'visible'}):
            with self.assertRaises(ValueError):
                s.validate_presence(result)
        with self.assertRaises(ValueError):
            s.capture_camera('example.com/path')

    def test_injected_key_overrides_environment_for_one_request(self):
        answer = {'red': 'uncertain', 'green': 'uncertain', 'blue': 'uncertain', 'pickup_area_visible': False, 'evidence': 'occluded'}
        raw = json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(answer)}]}}]}).encode()
        with patch.dict(s.os.environ, {'GEMINI_API_KEY': 'old-test-key'}), patch.object(s, 'urlopen', return_value=io.BytesIO(raw)) as request:
            s.ask_gemini('inspect', s.PRESENCE_SCHEMA, api_key='injected-test-key')
            headers = {k.lower(): v for k,v in request.call_args.args[0].header_items()}
            self.assertEqual(headers['x-goog-api-key'], 'injected-test-key')
            self.assertEqual(s.os.environ['GEMINI_API_KEY'], 'old-test-key')


if __name__ == '__main__':
    unittest.main()
