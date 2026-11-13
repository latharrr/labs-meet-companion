"""Independent regression expectations. Synthetic only; no provider calls."""
import unittest
from labs_meet.core import named_question

class BotIdentityTests(unittest.TestCase):
    def test_joined_display_name_does_not_self_trigger(self):
        self.assertIsNone(named_question('@Lathar Labs summarize decisions','Lathar Labs | Notes'))
    def test_legacy_display_name_does_not_self_trigger(self):
        self.assertIsNone(named_question('@Lathar Labs summarize decisions','Lathar Labs'))
    def test_human_question_still_works(self):
        self.assertEqual(named_question('@Lathar Labs summarize decisions','Synthetic participant'),'summarize decisions')
    def test_different_human_name_not_suppressed(self):
        self.assertEqual(named_question('@Lathar Labs summarize decisions','Lathar Labs contributor'),'summarize decisions')
if __name__=='__main__':unittest.main()
