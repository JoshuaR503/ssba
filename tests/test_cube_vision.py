import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cv2
import numpy as np
from cube_vision import detect, choose_stable
from test_pickup_without_id4 import payload, build_steps


class VisionTests(unittest.TestCase):
    def scene(self):
        image=np.zeros((160,420,3),dtype=np.uint8)
        zones=[]
        for name,x,bgr,distance in [('red',10,(0,0,255),30),('minus32',150,(0,255,0),20),('plus32',290,(255,0,0),10)]:
            image[40:100,x:x+60]=bgr
            center=cv2.cvtColor(np.uint8([[bgr]]),cv2.COLOR_BGR2LAB)[0,0].tolist()
            zones.append({'cube':name,'roi':[x,40,60,60],'lab_center':center,'distance_cm':distance})
        return image,{'image_size':[420,160],'zones':zones}

    def test_nearest_calibrated_station_and_absent_cube(self):
        image,config=self.scene()
        found=detect(image,config)
        self.assertEqual(len(found),3)
        self.assertEqual(choose_stable([found]*3)['cube'],'plus32')
        image[40:100,290:350]=0
        found=detect(image,config)
        self.assertEqual(choose_stable([found]*3)['cube'],'minus32')

    def test_no_cube_no_selection(self):
        image,config=self.scene()
        self.assertIsNone(choose_stable([detect(np.zeros_like(image),config)]*3))

    def test_distraction_outside_zone_ignored(self):
        image,config=self.scene();image[110:155,10:70]=(0,0,255)
        self.assertEqual(len(detect(image,config)),3)

    def test_unstable_track_rejected(self):
        a=[{'cube':'red','center':[10,10],'distance_cm':5}]
        b=[{'cube':'red','center':[40,10],'distance_cm':5}]
        self.assertIsNone(choose_stable([a,a,b]))

    def test_motion_constraints_all_selected_paths(self):
        for selection in ['deposition','metrology','etch']:
            for i,(_,joints) in enumerate(build_steps(selection),1):
                self.assertNotIn(4,payload(joints,i)['params'][1::2])
        for j in [{3:29},{4:0},{2:0},{3:float('nan')}]:
            with self.assertRaises(ValueError):payload(j,1)


if __name__=='__main__':unittest.main()
