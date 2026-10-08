import pytest

from app.services.financial.formulas import emi, future_value, outstanding_after


def test_emi_matches_hand_calculation():
    # P=6,00,000 at 10% for 72 months: r=0.10/12, EMI = P·r·(1+r)^n/((1+r)^n−1) ≈ 11,115.
    assert emi(600_000, 0.10, 72) == pytest.approx(11_115.0, abs=1.0)


def test_emi_zero_interest_is_straight_division():
    assert emi(120_000, 0.0, 12) == pytest.approx(10_000)


def test_emi_rejects_non_positive_tenure():
    with pytest.raises(ValueError):
        emi(100_000, 0.1, 0)


def test_outstanding_is_principal_before_any_payment_and_zero_at_end():
    assert outstanding_after(600_000, 0.10, 72, 0) == pytest.approx(600_000)
    assert outstanding_after(600_000, 0.10, 72, 72) == pytest.approx(0, abs=0.01)
    assert outstanding_after(600_000, 0.10, 72, 500) == pytest.approx(0, abs=0.01)


def test_outstanding_decreases_monotonically():
    balances = [outstanding_after(600_000, 0.10, 72, k) for k in range(73)]
    assert all(a > b for a, b in zip(balances, balances[1:], strict=False))


def test_outstanding_zero_interest_is_linear():
    assert outstanding_after(120_000, 0.0, 12, 3) == pytest.approx(90_000)


def test_future_value_zero_rate_is_simple_sum():
    assert future_value(200_000, 15_000, 0.0, 24) == pytest.approx(560_000)


def test_future_value_with_growth_exceeds_contributions():
    fv = future_value(0, 10_000, 0.12, 12)
    # 1% monthly: 10,000 × ((1.01^12 − 1)/0.01) ≈ 1,26,825
    assert fv == pytest.approx(126_825, abs=1)
