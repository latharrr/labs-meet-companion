from pathlib import Path
import unittest
from labs_meet.core import Segment, delivery_text, minutes

class UIContract(unittest.TestCase):
    def test_no_remote_scripts_or_fonts(self):
        root=Path(__file__).parent.parent/'labs_meet/static'
        for p in root.iterdir():
            if p.suffix in ('.html','.css','.js'):
                t=p.read_text();self.assertNotIn('src="https://',t);self.assertNotIn('url(https://',t);self.assertNotIn('fetch("https://',t)
    def test_transcript_not_injected_as_html(self):
        t=(Path(__file__).parent.parent/'labs_meet/static/app.js').read_text()
        self.assertNotIn('innerHTML',t);self.assertIn('textContent',t)
    def test_long_draft_keeps_transcript(self):
        segs=[Segment(str(i),i,i+1,'test words '*100,'Demo') for i in range(50)]
        text=delivery_text('A',minutes(segs),segs)
        self.assertIn('[49.0s]',text);self.assertGreater(len(text),4096)
