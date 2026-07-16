import unittest

from hedging.composite import CompositeStrategy, ForwardLeg


class CompositeStrategyTests(unittest.TestCase):
    def test_multiple_forward_legs_and_uncovered_remainder(self):
        strategy = CompositeStrategy(
            "分层远期",
            [ForwardLeg(0.40, 6.74), ForwardLeg(0.30, 6.76)],
        )
        result = strategy.calculate(1_000_000, 6.60)
        self.assertAlmostEqual(result.covered_ratio, 0.70)
        self.assertAlmostEqual(result.uncovered_ratio, 0.30)
        self.assertAlmostEqual(result.total_income_cny, 6_704_000)
        self.assertAlmostEqual(result.difference_cny, 104_000)

    def test_income_range_falls_as_coverage_rises(self):
        open_strategy = CompositeStrategy("不套保", [])
        hedge_strategy = CompositeStrategy("80%远期", [ForwardLeg(0.80, 6.74)])
        open_curve = open_strategy.scenario_curve(1_000_000, 6.40, 7.10)
        hedge_curve = hedge_strategy.scenario_curve(1_000_000, 6.40, 7.10)
        open_range = open_curve[-1].income_cny - open_curve[0].income_cny
        hedge_range = hedge_curve[-1].income_cny - hedge_curve[0].income_cny
        self.assertAlmostEqual(open_range, 700_000)
        self.assertAlmostEqual(hedge_range, 140_000)

    def test_overhedge_validation(self):
        with self.assertRaisesRegex(ValueError, "过度套保"):
            CompositeStrategy(
                "错误组合",
                [ForwardLeg(0.70, 6.74), ForwardLeg(0.50, 6.76)],
            )


if __name__ == "__main__":
    unittest.main()
