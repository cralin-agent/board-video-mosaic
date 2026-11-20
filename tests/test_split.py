"""Packing boundary tests: force each mosaic into its own under-limit ZIP."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from pipeline import process_video

class SplitTests(unittest.TestCase):
    def test_strict_zip_ceiling_and_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            video=root/"fake.mp4"
            video.write_bytes(b"test-fixture")
            def frames(*args,**kwargs):
                for i in range(12):
                    yield i,np.zeros((64,64,3),dtype=np.uint8)
            with patch("pipeline.video_meta",return_value=(64,64)), \
                 patch("pipeline.frames_1fps",side_effect=frames), \
                 patch("pipeline.encode_avif",return_value=(b"x"*80000,{"quality":55,"gate":"test"})):
                result=process_video(video,root,root/"out",
                        algorithm="avif",adaptive=False,max_bytes=350000,
                        callback=lambda msg:None)
            self.assertEqual(result["frames"],12)
            self.assertEqual(result["mosaics"],3)
            self.assertEqual(len(result["parts"]),3)
            all_seconds=[]
            for part in result["parts"]:
                p=root/"out"/next((root/"out").iterdir()).name/"avif"/part["file"]
                self.assertLess(p.stat().st_size,350000)
                self.assertLess(p.stat().st_size,100000000)
                with zipfile.ZipFile(p) as z:
                    self.assertIsNone(z.testzip())
                    payload=json.loads(z.read("manifest.json"))
                    for item in payload["mosaics"]:
                        all_seconds+=item["seconds"]
            self.assertEqual(all_seconds,list(range(12)))
if __name__=="__main__":unittest.main()
