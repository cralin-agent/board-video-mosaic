"""End-to-end fixture: two actual MPEG-4 videos -> mosaics -> zipped packages."""
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
import imageio_ffmpeg
import numpy as np
from PIL import Image,ImageDraw
from pipeline import run_folder

class Integration(unittest.TestCase):
    def test_dual_codec_and_batch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for folder,count in [(root/"one",8),(root/"two",5)]:
                folder.mkdir()
                frames=folder/"frames";frames.mkdir()
                for i in range(count):
                    im=Image.new("RGB",(160,96),(13,75,26))
                    dr=ImageDraw.Draw(im)
                    dr.line((12,40,130,40),fill="white",width=2)
                    dr.text((12,10),f"Step {i}",fill="white")
                    im.save(frames/f"{i:03}.png")
                ff=imageio_ffmpeg.get_ffmpeg_exe()
                p=subprocess.run([ff,"-hide_banner","-loglevel","error","-y",
                   "-framerate","1","-i",str(frames/"%03d.png"),"-c:v","mpeg4",
                   "-pix_fmt","yuv420p",str(folder/"same.mp4")],capture_output=True)
                self.assertEqual(p.returncode,0,p.stderr)
            for codec in ("avif","dsh"):
                result=run_folder(root,algorithm=codec,
                    output=root/("out_"+codec),adaptive=False,max_bytes=400000)
                self.assertEqual(len(result["results"]),2)
                for entry in result["results"]:
                    self.assertEqual(entry["status"],"ok",entry)
                    m=entry["result"]
                    self.assertIn(m["frames"],(5,8))
                    self.assertEqual(m["mosaics"],(m["frames"]+3)//4)
                    base=(root/("out_"+codec))
                    dirs=list(base.glob("*_*/manifest.json"))
                    self.assertEqual(len(dirs),2)
                    for d in dirs:
                        local=json.loads(d.read_text())
                        self.assertGreater(len(local["parts"]),0)
                        for part in local["parts"]:
                            z=d.parent/part["file"]
                            self.assertLess(z.stat().st_size,100_000_000)
                            with zipfile.ZipFile(z) as package:
                                self.assertIsNone(package.testzip())
                                self.assertIn("index.html",package.namelist())
                                self.assertIn("manifest.json",package.namelist())
                                imgs=[n for n in package.namelist() if n.startswith("mosaics/")]
                                self.assertTrue(imgs)
if __name__=="__main__":unittest.main()
