import unittest

from b_pilot import validate_papers, validate_target


class PilotValidationTest(unittest.TestCase):
    def setUp(self):
        self.paper = {
            'paper_id': 'cvf:ICCV2023:Example_2023_ICCV',
            'title': 'Example', 'authors': ['A Author'],
            'cvf_url': 'https://openaccess.thecvf.com/content/ICCV2023/html/Example_2023_ICCV_paper.html',
            'conference': 'ICCV', 'conference_year': 2023, 'owner': 'B',
        }

    def test_accepts_valid_and_rejects_duplicate_or_mismatched_records(self):
        self.assertEqual(validate_papers([self.paper]), [self.paper])
        with self.assertRaises(ValueError):
            validate_papers([self.paper, self.paper])
        with self.assertRaises(ValueError):
            validate_papers([{**self.paper, 'owner': 'A'}])
        with self.assertRaises(ValueError):
            validate_papers([{**self.paper, 'cvf_url': self.paper['cvf_url'].replace('Example', 'Other')}])
        with self.assertRaises(ValueError):
            validate_papers([{**self.paper, 'authors': []}])

    def test_accepts_official_slug_with_hyphen(self):
        paper = {**self.paper,
                 'paper_id': 'cvf:ICCV2023:Transformer-based_ICCV_2023',
                 'cvf_url': 'https://openaccess.thecvf.com/content/ICCV2023/html/Transformer-based_ICCV_2023_paper.html'}
        self.assertEqual(validate_papers([paper]), [paper])

    def test_only_isolated_target_is_allowed(self):
        validate_target('bolt://127.0.0.1:17687', 'neo4j')
        with self.assertRaises(ValueError):
            validate_target('bolt://127.0.0.1:7687', 'neo4j')
        with self.assertRaises(ValueError):
            validate_target('bolt://127.0.0.1:17687', 'system')


if __name__ == '__main__':
    unittest.main()
