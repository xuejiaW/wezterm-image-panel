import unittest

from scripts.check_commits import findings


class CommitMessageTests(unittest.TestCase):
    def test_scoped_change_explains_its_motivation(self):
        self.assertEqual(findings('refactor(packaging): isolate runtime modules\n\n'
                                  'Keep development tools outside the installed package.'), [])
        self.assertEqual(findings('docs: explain how to open the panel'), [])

    def test_original_unstructured_message_is_rejected(self):
        self.assertTrue(findings('Publish WezTerm Image Panel with native Windows support'))

    def test_header_prefix_alone_does_not_satisfy_angular_body_rule(self):
        self.assertTrue(findings('fix(terminal): decode buffered arrow keys'))
        self.assertTrue(findings('fix(terminal): decode buffered arrow keys\n\nBREAKING CHANGE: explain a migration here'))
        self.assertTrue(findings('chore: update files\n\nExplain why the change is needed.'))

    def test_summary_style_and_body_separation_are_checked(self):
        for message in ('docs: Explain the panel', 'docs: explain the panel.',
                        'fix: handle input\nExplain why this change is necessary.'):
            with self.subTest(message=message):
                self.assertTrue(findings(message))
