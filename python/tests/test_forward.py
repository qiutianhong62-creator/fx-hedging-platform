import unittest

from hedging.forward import ForwardHedge, ForwardInputs


class ForwardHedgeTests(unittest.TestCase):
    def test_49_percent_hedge_at_640(self):
        result = ForwardHedge(
            ForwardInputs(
                exposure_usd=1_000_000,
                hedge_ratio=0.49,
                forward_rate=6.74,
                maturity_spot=6.40,
            )
        ).calculate()
        self.assertAlmostEqual(result.hedged_usd, 490_000)
        self.assertAlmostEqual(result.total_income_cny, 6_566_600)
        self.assertAlmostEqual(result.difference_cny, 166_600)

    def test_70_percent_hedge_at_690(self):
        result = ForwardHedge(
            ForwardInputs(1_000_000, 0.70, 6.74, 6.90)
        ).calculate()
        self.assertAlmostEqual(result.total_income_cny, 6_788_000)
        self.assertAlmostEqual(result.difference_cny, -112_000)

    def test_ratio_validation(self):
        with self.assertRaises(ValueError):
            ForwardHedge(ForwardInputs(1_000_000, 1.20, 6.74, 6.60))


if __name__ == "__main__":
    unittest.main()
