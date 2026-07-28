import unittest

from app.rag.chat import _regex_negation_terms
from app.rag.search import _NON_LITERAL_TERMS, _term_pattern, clean_query_for_embedding


class NegationTests(unittest.TestCase):
    def test_term_pattern_word_boundaries(self) -> None:
        pat = _term_pattern("nut")
        self.assertIsNotNone(pat.search("cashew nut snack"))
        self.assertIsNotNone(pat.search("nut mix"))
        self.assertIsNone(pat.search("nutmeg powder"))
        self.assertIsNone(pat.search("walnut brownie"))
        self.assertIsNone(pat.search("coconut milk"))

    def test_term_pattern_handles_ampersand_apostrophe(self) -> None:
        pat = _term_pattern("M&M's")
        self.assertIsNotNone(pat.search("M&M's chocolate pack"))
        self.assertIsNone(pat.search("M&Ms chocolate pack"))

    def test_term_pattern_handles_hyphenated_terms(self) -> None:
        pat = _term_pattern("sugar-free")
        self.assertIsNotNone(pat.search("sugar-free dark chocolate"))
        self.assertIsNone(pat.search("sugar free dark chocolate"))

    def test_clean_query_removes_negated_term(self) -> None:
        cleaned = clean_query_for_embedding(
            "almond chocolates, not Lindt, dark chocolates",
            ["Lindt"],
        )
        self.assertNotIn("Lindt", cleaned)
        self.assertEqual(cleaned, "almond chocolates, dark chocolates")

    def test_regex_backstop_captures_short_negation(self) -> None:
        terms = _regex_negation_terms("I want almond chocolates, but not from Lindt")
        self.assertEqual(terms, ["Lindt"])

    def test_regex_backstop_strips_intensifier(self) -> None:
        terms = _regex_negation_terms("nothing too sweet please")
        self.assertEqual(terms, ["sweet"])

    def test_non_literal_term_does_not_match_literal_filtering(self) -> None:
        self.assertIn("expensive", _NON_LITERAL_TERMS)
        haystack = "Dark chocolate with almonds and premium cocoa"
        self.assertIsNone(_term_pattern("expensive").search(haystack))


if __name__ == "__main__":
    unittest.main()
