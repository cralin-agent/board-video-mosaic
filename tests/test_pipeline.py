import io
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from algorithms import dsh_tile,encode_avif
from pipeline import MAX_BYTES,video_output_dir,viewer_html
class Tests(unittest.TestCase):
    def test_binary_and_fallback(self):
        a=np.zeros((80,120,3),dtype=np.uint8)
        a[:]=[15,70,22]
        a[25:50,40:70]=255
        tile,kind=dsh_tile(a)
        self.assertEqual(tile.size,(120,80))
        self.assertIn(kind,("binary","fallback-rgb"))
        white=np.full_like(a,255)
        tile,kind=dsh_tile(white)
        self.assertEqual(kind,"fallback-rgb")
    def test_avif_decode(self):
        a=Image.fromarray(np.random.default_rng(7).integers(0,256,(80,120,3),dtype=np.uint8))
        data,met=encode_avif(a,adaptive=False)
        self.assertEqual(Image.open(io.BytesIO(data)).size,(120,80))
        self.assertEqual(met["quality"],55)
    def test_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/"BoardPackages"
            a=video_output_dir(root/"a"/"same.mp4",root,out)
            b=video_output_dir(root/"b"/"same.mp4",root,out)
            self.assertNotEqual(a,b)
    def test_viewer(self):
        self.assertIn("mosaics/",viewer_html([{"file":"mosaics/a.avif","seconds":[0]}]))
    def test_budget(self):
        self.assertLess(MAX_BYTES,100_000_000)
if __name__=="__main__":unittest.main()
