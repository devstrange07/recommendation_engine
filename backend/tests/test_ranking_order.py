"""Unit tests for deterministic ranking_order hard-assert."""

from __future__ import annotations

import unittest

from app.evals.judge import apply_ranking_order_hard_fail, ranking_order_check
from app.evals.models import RankingOrderExpectation, RubricDimensionScore, TurnRubric


def _hit(hid: str, rank: int, *, title: str = "", price: float | None = None) -> dict:
    excerpt: dict = {"title": title}
    if price is not None:
        excerpt["price_min"] = {"INR": price}
    return {"id": hid, "rrf_rank": rank, "payload_excerpt": excerpt}


class RankingOrderCheckTests(unittest.TestCase):
    def test_price_asc_example_b_fails(self) -> None:
        # Example B: cheapest Maruti — diesel 742k ranked above petrol 650k
        hits = [
            _hit("auto_005", 1, title="Swift Base Diesel", price=742000),
            _hit("auto_001", 2, title="Swift Base Petrol", price=650000),
            _hit("auto_009", 3, title="Swift S Diesel", price=829000),
            _hit("auto_017", 4, title="Swift VX Diesel", price=1003000),
            _hit("auto_013", 5, title="Swift V Diesel", price=916000),
            _hit("auto_026", 7, title="Baleno Base Petrol", price=650000),
        ]
        spec = RankingOrderExpectation(
            field="price_min",
            direction="asc",
            apply_if=["cheapest", "lowest price", "sorted from lowest"],
        )
        msg = (
            "I'm a first-time buyer, so the cheaper the better — could you show me "
            "the cheapest Maruti Suzuki hatchbacks you have, sorted from lowest price up?"
        )
        applies, ok, reason = ranking_order_check(hits, spec, msg)
        self.assertTrue(applies)
        self.assertFalse(ok)
        self.assertIn("asc violated", reason)

    def test_title_kwh_desc_example_a_fails(self) -> None:
        hits = [
            _hit("auto_948", 1, title="MG ZS EV 77kWh - Titan Grey"),
            _hit("auto_915", 2, title="MG Comet EV 50kWh - Ruby Red"),
            _hit("auto_949", 3, title="MG ZS EV 77kWh - Deep Blue"),
            _hit("auto_914", 4, title="MG Comet EV 50kWh - Deep Blue"),
            _hit("auto_801", 6, title="Tata Tiago EV 30kWh - Arctic White"),
        ]
        spec = RankingOrderExpectation(
            field="title_kwh",
            direction="desc",
            apply_if=["biggest battery", "largest battery", "highest"],
        )
        msg = (
            "Show me electric SUVs with the biggest battery. fuel: electric. "
            "body_type: SUV. battery capacity: highest (77 kWh)"
        )
        applies, ok, reason = ranking_order_check(hits, spec, msg)
        self.assertTrue(applies)
        self.assertFalse(ok)
        self.assertIn("desc violated", reason)

    def test_apply_if_non_match_skips_budget_turn(self) -> None:
        hits = [
            _hit("auto_005", 1, title="Swift Base Diesel", price=742000),
            _hit("auto_001", 7, title="Swift Base Petrol", price=650000),
        ]
        spec = RankingOrderExpectation(
            field="price_min",
            direction="asc",
            apply_if=["cheapest", "lowest price", "sorted from lowest"],
        )
        msg = "Maruti Suzuki cars with manual transmission under 8 lakh. brand: Maruti Suzuki."
        applies, ok, reason = ranking_order_check(hits, spec, msg)
        self.assertFalse(applies)
        self.assertTrue(ok)
        self.assertIn("apply_if", reason)

    def test_monotonic_asc_passes(self) -> None:
        hits = [
            _hit("a", 1, price=650000),
            _hit("b", 2, price=650000),
            _hit("c", 3, price=742000),
        ]
        spec = RankingOrderExpectation(field="price_min", direction="asc")
        applies, ok, _ = ranking_order_check(hits, spec, "any")
        self.assertTrue(applies)
        self.assertTrue(ok)

    def test_hard_fail_overrides_rubric(self) -> None:
        hits = [
            _hit("auto_005", 1, title="Swift Diesel", price=742000),
            _hit("auto_001", 2, title="Swift Petrol", price=650000),
        ]
        soft = {
            "ranking_order": {
                "field": "price_min",
                "direction": "asc",
                "apply_if": ["cheapest"],
            }
        }
        rubric = TurnRubric(
            **{"pass": True},
            scores=[
                RubricDimensionScore(dimension="ranking_relevance", **{"pass": True}, reasoning="soft ok"),
                RubricDimensionScore(dimension="tool_args", **{"pass": True}, reasoning="ok"),
            ],
            reasoning="overall soft pass",
            judge_source="openai_fallback",
        )
        out = apply_ranking_order_hard_fail(
            rubric,
            hits=hits,
            soft_expectations=soft,
            user_message="show me the cheapest options",
        )
        self.assertFalse(out.pass_)
        ranking = next(s for s in out.scores if s.dimension == "ranking_relevance")
        self.assertFalse(ranking.pass_)
        self.assertIn("asc violated", ranking.reasoning)


if __name__ == "__main__":
    unittest.main()
