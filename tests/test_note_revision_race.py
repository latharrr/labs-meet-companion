import tempfile
from pathlib import Path
import unittest
from labs_meet.core import Segment
from labs_meet.store import Store
from labs_meet.service import Companion

class NoteRevisionTests(unittest.TestCase):
    def test_changed_transcript_during_generation_cannot_save_current_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'state.db')
            mid=store.create('Synthetic','abc-defg-hij','Synthetic consent')
            store.ingest(mid,[Segment('a',0,1,'Original synthetic fact','Synthetic')])
            class RevisingAI:
                def minutes(self,rows):
                    store.ingest(mid,[Segment('a',0,1,'Corrected synthetic fact','Synthetic')])
                    return {'summary':[{'text':'Original synthetic fact'}],'decisions':[],'actions':[]}
            with self.assertRaises(ValueError):Companion(store,ai=RevisingAI()).generate_notes(mid)
            self.assertIsNone(store.ai_notes(mid));store.db.close()
if __name__=='__main__':unittest.main()
