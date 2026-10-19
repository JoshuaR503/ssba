"""Offline regression tests for open-gripper interactive positioning."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import calibration as c


class PositioningTests(unittest.TestCase):
    def test_all_targets_open_and_exact_pickup_height(self):
        data=c.configuration()
        for station in c.COLORS:
            steps=c.positioning_steps(station,data)
            self.assertEqual(len(steps),3 if station=='deposition' else 6)
            expected={int(k):v for k,v in data['stations'][station]['pickup'].items()}
            if station=='etch':expected[3]=76
            self.assertEqual(next(j for label,j in steps if label.startswith('PICKUP HEIGHT')),{**expected,1:data['stations'][station]['open']})
            for _,joints in steps:
                self.assertNotIn(4,joints)
                self.assertEqual(joints[1],data['stations'][station]['open'])
                if 3 in joints:self.assertGreaterEqual(joints[3],30)

    def test_deposition_base_is_full_pose_previously_reached_at_step_five(self):
        steps=c.positioning_steps('deposition',c.configuration())
        expected={1:-30,3:74,5:-33.5,6:-4}
        self.assertEqual(steps[0][1],expected)
        self.assertEqual(steps[-1][1],expected)
        state={}
        for _,joints in steps[:5]:state.update(joints)
        self.assertEqual(state,expected)

    def test_all_calibration_starts_and_returns_use_chosen_raised_base(self):
        data=c.configuration()
        for station in c.COLORS:
            steps=c.positioning_steps(station,data)
            expected={1:data['stations'][station]['open'],3:74,5:-33.5,6:-4}
            self.assertEqual(steps[0][1],expected)
            self.assertEqual(steps[-1][1],expected)
            self.assertEqual(steps[-2][1][6],-4)
            for _,joints in steps:
                self.assertFalse(joints.get(3)==48 and joints.get(5)==4 and joints.get(6)==0)

    def test_compaction_keeps_final_poses_and_only_changes_next_gripper_at_base(self):
        data=c.configuration();state={};counts=[]
        for station in c.COLORS:
            steps=c.positioning_steps(station,data,state)
            counts.append(len(steps))
            if state:
                self.assertEqual(steps[0][0],'OPEN approach above pickup')
                self.assertEqual(steps[0][1][1],data['stations'][station]['open'])
            for _,joints in steps:
                self.assertTrue(any(state.get(k)!=v for k,v in joints.items()))
                state.update(joints)
            self.assertEqual(state,{1:data['stations'][station]['open'],3:74,5:-33.5,6:-4})
        self.assertEqual(counts,[3,5,5])
        # Retain both the real raised clearance and the etch wrist=80 setting.
        etch=c.positioning_steps('etch',data)
        self.assertEqual(etch[3][1][3],80)

    def test_preview_never_moves(self):
        with patch.object(sys,'argv',['calibration.py']),patch.object(c,'send_move') as move,patch('builtins.input') as prompt,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(),0)
            move.assert_not_called();prompt.assert_not_called()

    def test_all_stations_require_go_before_every_move(self):
        moves_at_pause=[]
        with patch.object(sys,'argv',['calibration.py','--go']),patch.object(c,'send_move') as move,contextlib.redirect_stdout(io.StringIO()):
            def advance(_):
                moves_at_pause.append(move.call_count)
                return 'go'
            with patch('builtins.input',side_effect=advance):
                self.assertEqual(c.main(),0)
            self.assertEqual(move.call_count,13)
        self.assertEqual(moves_at_pause,list(range(13)))

    def test_execute_flag_executes_all_moves_without_prompts(self):
        with patch.object(sys,'argv',['calibration.py','--execute']),patch.object(c,'send_move') as move,patch('builtins.input') as prompt,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(),0)
            self.assertEqual(move.call_count,13)
            prompt.assert_not_called()

    def test_pickup_stop_then_quit_does_not_retract_or_grip(self):
        with patch.object(sys,'argv',['calibration.py','--cube','etch','--go']),patch.object(c,'send_move') as move,patch('builtins.input',side_effect=['go','go','go','q']),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(),0)
            self.assertEqual(move.call_count,3)
            self.assertEqual(move.call_args.args[1],{3:76,5:-60,6:32,1:-42})

    def test_enter_does_not_move(self):
        with patch.object(sys,'argv',['calibration.py','--go']),patch.object(c,'send_move') as move,patch('builtins.input',return_value=''),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(),0)
            move.assert_not_called()

    def test_error_stops_without_automatic_return(self):
        with patch.object(sys,'argv',['calibration.py','--go']),patch.object(c,'send_move',side_effect=OSError('test unreachable')) as move,patch('builtins.input',return_value='go'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(c.main(),1)
            self.assertEqual(move.call_count,1)


if __name__=='__main__':unittest.main()
