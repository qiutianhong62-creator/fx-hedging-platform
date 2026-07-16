import unittest

from hedging.option import (
    CurrencyOption,
    ExposureDirection,
    OptionInputs,
    OptionPosition,
    OptionType,
)


class CurrencyOptionTests(unittest.TestCase):
    def test_buy_put_protects_usd_receivable(self):
        result = CurrencyOption(
            OptionInputs(
                notional_usd=1_000_000,
                option_type=OptionType.PUT,
                position=OptionPosition.BUY,
                strike_rate=6.70,
                premium_rate_cny_per_usd=0.05,
                maturity_spot=6.40,
                exposure_direction=ExposureDirection.RECEIVABLE,
            )
        ).calculate()
        self.assertAlmostEqual(result.intrinsic_value_cny, 300_000)
        self.assertAlmostEqual(result.premium_cashflow_cny, -50_000)
        self.assertAlmostEqual(result.net_option_cashflow_cny, 250_000)
        self.assertAlmostEqual(result.final_cashflow_cny, 6_650_000)
        self.assertAlmostEqual(result.break_even_rate, 6.65)

    def test_buy_call_caps_usd_payable_cost(self):
        result = CurrencyOption(
            OptionInputs(
                notional_usd=1_000_000,
                option_type=OptionType.CALL,
                position=OptionPosition.BUY,
                strike_rate=6.75,
                premium_rate_cny_per_usd=0.06,
                maturity_spot=7.00,
                exposure_direction=ExposureDirection.PAYABLE,
            )
        ).calculate()
        self.assertAlmostEqual(result.intrinsic_value_cny, 250_000)
        self.assertAlmostEqual(result.net_option_cashflow_cny, 190_000)
        self.assertAlmostEqual(result.final_cashflow_cny, 6_810_000)
        self.assertAlmostEqual(result.break_even_rate, 6.81)

    def test_sell_call_caps_usd_receivable_upside(self):
        result = CurrencyOption(
            OptionInputs(
                notional_usd=1_000_000,
                option_type=OptionType.CALL,
                position=OptionPosition.SELL,
                strike_rate=6.90,
                premium_rate_cny_per_usd=0.03,
                maturity_spot=7.10,
                exposure_direction=ExposureDirection.RECEIVABLE,
            )
        ).calculate()
        self.assertAlmostEqual(result.net_option_cashflow_cny, -170_000)
        self.assertAlmostEqual(result.final_cashflow_cny, 6_930_000)
        self.assertIn("很大的履约损失", CurrencyOption(
            OptionInputs(
                1_000_000,
                OptionType.CALL,
                OptionPosition.SELL,
                6.90,
                0.03,
                7.10,
                ExposureDirection.RECEIVABLE,
            )
        ).risk_description())

    def test_sell_put_limits_payable_downside_benefit(self):
        result = CurrencyOption(
            OptionInputs(
                notional_usd=1_000_000,
                option_type=OptionType.PUT,
                position=OptionPosition.SELL,
                strike_rate=6.65,
                premium_rate_cny_per_usd=0.025,
                maturity_spot=6.40,
                exposure_direction=ExposureDirection.PAYABLE,
            )
        ).calculate()
        self.assertAlmostEqual(result.net_option_cashflow_cny, -225_000)
        self.assertAlmostEqual(result.final_cashflow_cny, 6_625_000)

    def test_option_input_validation(self):
        with self.assertRaises(ValueError):
            CurrencyOption(
                OptionInputs(
                    1_000_000,
                    OptionType.PUT,
                    OptionPosition.BUY,
                    6.70,
                    -0.01,
                    6.40,
                    ExposureDirection.RECEIVABLE,
                )
            )


if __name__ == "__main__":
    unittest.main()
