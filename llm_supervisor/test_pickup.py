"""Mocked checkpoint integration; no physical robot, images or paid API calls."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pickup as p
import supervisor as ai


class CheckpointTests(unittest.TestCase):
    def results(self):
        return [
            ({'status': 'visible', 'pickup_area_visible': True, 'evidence': 'cube on tabletop'}, 0.1),
            ({'status': 'likely_carrying', 'evidence': 'matching green fragment near camera'}, 0.1),
            ({'status': 'likely_released', 'evidence': 'target appears in tray'}, 0.1),
        ]

    def run_cycle(self, results, **kwargs):
        events = []
        with patch.object(p, 'send_move') as move, patch.object(ai, 'capture_camera', return_value={'inlineData': {'data': 'test'}}) as camera, patch.object(p, 'assess', side_effect=results), __import__('contextlib').redirect_stdout(io.StringIO()):
            outcome = p.execute_station('deposition', p.configuration(), 'unused', ai.DEFAULT_MODEL, events.append, **kwargs)
        return outcome, move.call_count, camera.call_count, events

    def test_frozen_plan_matches_working_baseline_all_stations(self):
        path = Path(__file__).resolve().parents[1]/'scripts/test_pickup_without_id4.py'
        spec = importlib.util.spec_from_file_location('baseline_for_comparison', path)
        baseline = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)
        for station in ai.STATIONS:
            expected = [j for _, j in baseline.build_steps(station)]
            actual = [j for _, j in p.station_steps(station, p.configuration())]
            self.assertEqual(actual, expected)

    def test_passed_checkpoints_complete_compacted_moves(self):
        outcome, moves, frames, events = self.run_cycle(self.results())
        self.assertEqual(moves, 10); self.assertEqual(frames, 3)
        self.assertIn('completed', outcome)
        self.assertEqual([e['checkpoint'] for e in events if e['type']=='checkpoint'], ['approach','grip','release'])

    def test_approach_only_stops_after_two_moves(self):
        outcome, moves, frames, _ = self.run_cycle(self.results(), approach_only=True)
        self.assertEqual(moves, 2); self.assertEqual(frames, 1)
        self.assertEqual(outcome, 'approach_checked_only')

    def test_failed_checkpoints_reverse_to_start_without_forward_progress(self):
        for checkpoint, expected_moves in [(0,3),(1,5)]:
            results = self.results(); results[checkpoint] = ({'status': 'uncertain'}, 0.1)
            with patch.object(p, 'send_move') as move, patch.object(ai, 'capture_camera', return_value={}), patch.object(p, 'assess', side_effect=results), __import__('contextlib').redirect_stdout(io.StringIO()):
                with self.assertRaises(p.CheckpointPause):
                    p.execute_station('etch', p.configuration(), 'unused', ai.DEFAULT_MODEL, lambda e: None)
                calls = move.call_args_list
                self.assertEqual([call.args[2] for call in calls[:expected_moves]], list(range(1, expected_moves+1)))
                self.assertTrue(all(call.args[2] >= 1000 for call in calls[expected_moves:]))
                current = {int(k):v for k,v in p.configuration()['stations']['etch']['start'].items()}
                for call in calls:
                    current.update(call.args[1])
                start = {int(k):v for k,v in p.configuration()['stations']['etch']['start'].items()}
                self.assertEqual({k:current[k] for k in (3,5,6)}, {k:start[k] for k in (3,5,6)})
                if checkpoint < 2:
                    self.assertEqual(current[1],start[1])
                else:
                    self.assertEqual(current[1],p.configuration()['stations']['etch']['release'])
                    self.assertTrue(all(1 not in call.args[1] for call in calls[expected_moves:]))

    def test_camera_or_provider_error_stops_without_recovery(self):
        for failure in ('capture_camera', 'assess'):
            with patch.object(p, 'send_move') as move, patch.object(ai, 'capture_camera', return_value={}) as camera, patch.object(p, 'assess') as assess, __import__('contextlib').redirect_stdout(io.StringIO()):
                (camera if failure=='capture_camera' else assess).side_effect = OSError('test failure')
                with self.assertRaises(OSError):
                    p.execute_station('etch', p.configuration(), 'unused', ai.DEFAULT_MODEL, lambda e: None)
                self.assertEqual(move.call_count, 3)

    def test_non_tabletop_view_downgraded_to_uncertain(self):
        inventory = ai.validate_presence({'red':'absent','green':'absent','blue':'absent','pickup_area_visible':False,'evidence':'face/room only'})
        self.assertTrue(all(inventory[k]=='uncertain' for k in ('red','green','blue')))
        result = p.validate_checkpoint({'status':'visible','pickup_area_visible':False,'appearance_consistent':False,'evidence_type':'insufficient','evidence':'room'}, 'approach')
        self.assertEqual(result['status'],'uncertain')

    def test_uncertain_release_uses_normal_return_for_all_stations(self):
        for station in ai.STATIONS:
            results=self.results();results[2]=({'status':'uncertain','evidence':'cube cropped out'},.1)
            with patch.object(p,'send_move') as move,patch.object(ai,'capture_camera',return_value={}),patch.object(p,'assess',side_effect=results),__import__('contextlib').redirect_stdout(io.StringIO()):
                outcome=p.execute_station(station,p.configuration(),'unused',ai.DEFAULT_MODEL,lambda e:None)
            count=len(p.station_steps(station,p.configuration()))
            self.assertEqual(move.call_count,count)
            self.assertEqual([c.args[2] for c in move.call_args_list],list(range(1,count+1)))
            expected=[joints for _,joints in p.station_steps(station,p.configuration())]
            self.assertEqual([c.args[1] for c in move.call_args_list],expected)
            self.assertIn('release_observation_uncertain',outcome)

    def test_release_prompt_never_requires_fingers_or_source_target(self):
        raw={'status':'uncertain','evidence':'tray target cropped out'}
        with patch.object(ai,'ask_gemini',return_value=(raw,.2)) as ask:
            result,_=p.assess('release','deposition',{'text':'frame'})
            self.assertEqual(result,raw)
            self.assertEqual(ask.call_args.args[1],p.RELEASE_SCHEMA)
            self.assertIn('TRAY, not at the source',ask.call_args.args[0])

    def test_transport_fixed_500ms_and_constraints(self):
        with patch.object(p, 'urlopen', return_value=io.StringIO('{"result":[true]}')) as request, patch.object(p.time,'sleep') as sleep:
            p.send_move('robot.local',{3:48,5:4},1)
            self.assertEqual(json.loads(request.call_args.args[0].data)['params'],[500,3,48,5,4])
            sleep.assert_called_once_with(.65)
        for joints in ({4:0},{3:29},{5:float('nan')},{1:False}):
            with patch.object(p,'urlopen') as request:
                with self.assertRaises(ValueError):p.send_move('unused',joints,1)
                request.assert_not_called()

    def test_assessment_grip_preserves_before_after_order(self):
        raw={'status':'uncertain','target_color_visible_near_camera':False,'appearance_matches_before':False,'clearly_left_on_source':False,'evidence':'fragment outside view'}
        before,after={'text':'before'},{'text':'after'}
        with patch.object(ai,'ask_gemini',return_value=(raw,.2)) as ask:
            result,_=p.assess('grip','etch',after,before)
            self.assertEqual(ask.call_args.args[2],[before,after])
            self.assertEqual(result['status'],'uncertain')

    def test_recognizable_partial_target_allowed_at_approach(self):
        raw={'status':'visible','pickup_area_visible':True,'appearance_consistent':True,
             'evidence_type':'recognizable_partial_cube','evidence':'Partial green face and straight top edge at bottom of box.'}
        with patch.object(ai,'ask_gemini',return_value=(raw,.2)) as ask:
            result,_=p.assess('approach','deposition',{'text':'frame'})
            self.assertEqual(result['status'],'visible')
            self.assertIn('BOTTOM EDGE',ask.call_args.args[0])
            self.assertIn('green',ask.call_args.args[0])
        # The relaxed approach criterion must not modify the original targets.
        self.assertEqual(p.station_steps('deposition',p.configuration())[1][1],{3:74,5:-56,6:-4,1:-30})

    def test_expected_pose_does_not_override_wrong_color_or_insufficient_shape(self):
        for consistent,kind in [(False,'recognizable_partial_cube'),(True,'insufficient')]:
            raw={'status':'visible','pickup_area_visible':True,'appearance_consistent':consistent,
                 'evidence_type':kind,'evidence':'Unidentifiable colored strip or wrong-color object.'}
            self.assertEqual(p.validate_checkpoint(raw,'approach')['status'],'uncertain')

    def test_unknown_partial_evidence_label_rejected(self):
        with self.assertRaises(ValueError):
            p.validate_checkpoint({'status':'visible','pickup_area_visible':True,'appearance_consistent':True,
                                   'evidence_type':'assumed_from_pose','evidence':'at expected pose'},'approach')

    def test_failed_lift_lowers_before_reopening_at_source(self):
        results=self.results();results[1]=({'status':'uncertain'},.1)
        with patch.object(p,'send_move') as move,patch.object(ai,'capture_camera',return_value={}),patch.object(p,'assess',side_effect=results),__import__('contextlib').redirect_stdout(io.StringIO()):
            with self.assertRaises(p.CheckpointPause):
                p.execute_station('deposition',p.configuration(),'unused',ai.DEFAULT_MODEL,lambda e:None)
        reverse=[call.args[1] for call in move.call_args_list[4:]]
        self.assertEqual(reverse[0],{5:-56})
        self.assertEqual(reverse[1],{1:-30})

    def test_reverse_transport_failure_does_not_keep_moving(self):
        results=self.results();results[0]=({'status':'uncertain'},.1)
        with patch.object(p,'send_move',side_effect=[None,None,None,OSError('reverse lost connection')]) as move,patch.object(ai,'capture_camera',return_value={}),patch.object(p,'assess',side_effect=results),__import__('contextlib').redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                p.execute_station('etch',p.configuration(),'unused',ai.DEFAULT_MODEL,lambda e:None)
            self.assertEqual(move.call_count,4)

    def test_weak_carry_allows_matching_close_fragment_without_fingers(self):
        raw={'status':'likely_carrying','target_color_visible_near_camera':True,'appearance_matches_before':True,
             'clearly_left_on_source':False,'evidence':'Matching green face fragment remains at lower image edge.'}
        with patch.object(ai,'ask_gemini',return_value=(raw,.2)) as ask:
            result,_=p.assess('grip','deposition',{'text':'after'},{'text':'before'})
            self.assertEqual(result['status'],'likely_carrying')
            self.assertIn('not_confirmed_grip',result['verification_type'])
            self.assertEqual(ask.call_args.args[1],p.CARRY_SCHEMA)

    def test_weak_carry_rejects_missing_or_conflicting_color_evidence(self):
        for visible,matching in [(False,True),(True,False),(False,False)]:
            result=p.validate_carry({'status':'likely_carrying','target_color_visible_near_camera':visible,
                'appearance_matches_before':matching,'clearly_left_on_source':False,'evidence':'ambiguous view'})
            self.assertEqual(result['status'],'uncertain')
        result=p.validate_carry({'status':'likely_carrying','target_color_visible_near_camera':True,
            'appearance_matches_before':True,'clearly_left_on_source':True,'evidence':'target clearly on source'})
        self.assertEqual(result['status'],'not_carrying')

    def test_banned_upright_pose_rejected_and_all_active_bases_replaced(self):
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('baseline_ban_test',Path(__file__).resolve().parents[1]/'scripts/test_pickup_without_id4.py')
        baseline=module_from_spec(spec);spec.loader.exec_module(baseline)
        old={1:-40,3:48,5:4,6:0}
        with self.assertRaisesRegex(ValueError,'Banned'):p.validate_targets(old)
        with self.assertRaisesRegex(ValueError,'Banned'):baseline.payload(old,1)
        for station in ai.STATIONS:
            for joints in (p.station_steps(station,p.configuration())[0][1],baseline.build_steps(station)[0][1]):
                self.assertEqual({k:joints[k] for k in (3,5,6)},{3:74,5:-33.5,6:-4})

    def test_full_all_station_motion_matches_non_llm_runner(self):
        import tempfile
        spec=importlib.util.spec_from_file_location('baseline_all_compare',Path(__file__).resolve().parents[1]/'scripts/test_pickup_without_id4.py')
        baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
        data=p.configuration()
        for mode in ('--execute','--go'):
            with tempfile.TemporaryDirectory() as folder, patch.object(p,'ROOT',Path(folder)),patch.object(p,'configuration',return_value=data),patch.object(sys,'argv',['pickup.py',mode]),patch.object(ai,'local_api_key',return_value='test-only-key'),patch.object(ai,'capture_camera',return_value={}),patch.object(p,'assess',side_effect=self.results()*3),patch.object(p,'send_move') as move,patch('builtins.input',return_value='go') as prompt,__import__('contextlib').redirect_stdout(io.StringIO()):
                self.assertEqual(p.main(),0)
                self.assertEqual([call.args[1] for call in move.call_args_list],[j for _,j in baseline.build_steps()])
                self.assertEqual(move.call_count,30)
                self.assertEqual(prompt.call_count,30 if mode=='--go' else 0)

    def test_step_mode_quit_never_dispatches_first_move(self):
        with patch.object(p,'send_move') as move,patch('builtins.input',return_value='q'),__import__('contextlib').redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                p.execute_station('etch',p.configuration(),'unused',ai.DEFAULT_MODEL,lambda e:None,step_mode=True)
            move.assert_not_called()

    def test_first_camera_capture_is_at_exact_open_pickup_for_every_station(self):
        for station in ai.STATIONS:
            data=p.configuration();current={};seen=[]
            def move(host,joints,number):current.update(joints)
            def frame(host):
                seen.append(current.copy())
                return {}
            with patch.object(p,'send_move',side_effect=move),patch.object(ai,'capture_camera',side_effect=frame),patch.object(p,'assess',return_value=({'status':'visible'},.1)),__import__('contextlib').redirect_stdout(io.StringIO()):
                p.execute_station(station,data,'unused',ai.DEFAULT_MODEL,lambda e:None,approach_only=True)
            expected={int(k):v for k,v in data['stations'][station]['pickup'].items()}
            expected[1]=data['stations'][station]['open']
            self.assertEqual(seen,[expected])

    def test_preview_has_no_network(self):
        with patch.object(sys,'argv',['pickup.py']), patch.object(p,'urlopen') as robot, patch.object(ai,'urlopen') as api, __import__('contextlib').redirect_stdout(io.StringIO()):
            self.assertEqual(p.main(),0)
            robot.assert_not_called();api.assert_not_called()


if __name__=='__main__':unittest.main()
