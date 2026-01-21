"""
Tests for formatting module - runs without Fusion.

Run with: pytest tests/ -v
"""
import pytest

from core.formatting import (
    decimal_to_fraction,
    format_length,
    format_metric,
    gcd,
    get_precision_label,
)
from models.units import UnitConfig


class TestGcd:
    """Test greatest common divisor function."""

    def test_gcd_same_numbers(self) -> None:
        assert gcd(8, 8) == 8

    def test_gcd_coprime(self) -> None:
        assert gcd(7, 11) == 1

    def test_gcd_common_factor(self) -> None:
        assert gcd(12, 8) == 4

    def test_gcd_one(self) -> None:
        assert gcd(1, 5) == 1


class TestDecimalToFraction:
    """Test decimal to fraction conversion."""

    # Happy path tests
    def test_whole_number(self) -> None:
        assert decimal_to_fraction(5.0, 16) == "5"

    def test_simple_fraction_half(self) -> None:
        assert decimal_to_fraction(0.5, 16) == "1/2"

    def test_simple_fraction_quarter(self) -> None:
        assert decimal_to_fraction(0.25, 16) == "1/4"

    def test_simple_fraction_eighth(self) -> None:
        assert decimal_to_fraction(0.125, 16) == "1/8"

    def test_simple_fraction_sixteenth(self) -> None:
        assert decimal_to_fraction(0.0625, 16) == "1/16"

    def test_mixed_number(self) -> None:
        assert decimal_to_fraction(5.5, 16) == "5 1/2"

    def test_mixed_number_quarter(self) -> None:
        assert decimal_to_fraction(3.25, 16) == "3 1/4"

    def test_mixed_number_three_quarters(self) -> None:
        assert decimal_to_fraction(2.75, 16) == "2 3/4"

    def test_mixed_number_sixteenth(self) -> None:
        assert decimal_to_fraction(1.0625, 16) == "1 1/16"

    # Negative value tests (Issue 8 fix)
    def test_negative_whole_number(self) -> None:
        assert decimal_to_fraction(-5.0, 16) == "-5"

    def test_negative_fraction(self) -> None:
        assert decimal_to_fraction(-0.5, 16) == "-1/2"

    def test_negative_quarter(self) -> None:
        assert decimal_to_fraction(-0.25, 16) == "-1/4"

    def test_negative_mixed_number(self) -> None:
        assert decimal_to_fraction(-5.5, 16) == "-5 1/2"

    def test_negative_mixed_quarter(self) -> None:
        assert decimal_to_fraction(-3.25, 16) == "-3 1/4"

    # Zero tests
    def test_zero(self) -> None:
        assert decimal_to_fraction(0.0, 16) == "0"

    def test_zero_with_different_denominator(self) -> None:
        assert decimal_to_fraction(0.0, 8) == "0"

    # Exact mode (denominator = 0)
    def test_exact_mode_integer(self) -> None:
        assert decimal_to_fraction(5.0, 0) == "5.0000"

    def test_exact_mode_decimal(self) -> None:
        assert decimal_to_fraction(5.5, 0) == "5.5000"

    def test_exact_mode_negative(self) -> None:
        assert decimal_to_fraction(-3.14159, 0) == "-3.1416"

    # Different denominator tests
    def test_denominator_8(self) -> None:
        assert decimal_to_fraction(0.125, 8) == "1/8"

    def test_denominator_32(self) -> None:
        assert decimal_to_fraction(0.03125, 32) == "1/32"

    # Rounding tests
    def test_rounds_to_nearest(self) -> None:
        # 0.126 is closer to 1/8 (0.125) than to 3/16 (0.1875)
        assert decimal_to_fraction(0.126, 16) == "1/8"

    def test_rounds_up(self) -> None:
        # 0.15 is closer to 1/8 (0.125) when using denominator 8
        # but closer to 3/16 (0.1875) when using denominator 16
        # Actually 0.15 * 16 = 2.4, rounds to 2, which is 1/8
        assert decimal_to_fraction(0.15, 16) == "1/8"

    # Boundary tests
    def test_very_small_positive(self) -> None:
        # Very small value rounds to 0
        assert decimal_to_fraction(0.001, 16) == "0"

    def test_very_small_negative(self) -> None:
        # Very small negative value rounds to 0
        assert decimal_to_fraction(-0.001, 16) == "0"


# Test fixtures for UnitConfig
@pytest.fixture
def imperial_units() -> UnitConfig:
    """Create imperial (inch) unit configuration."""
    return UnitConfig(
        is_metric=False,
        unit_name='in',
        unit_symbol='"',
        cm_to_unit=1.0 / 2.54,
        default_tube_od='1.75',
        default_precision=16,
        valid_precisions=(0, 4, 8, 16, 32),
    )


@pytest.fixture
def metric_units() -> UnitConfig:
    """Create metric (mm) unit configuration."""
    return UnitConfig(
        is_metric=True,
        unit_name='mm',
        unit_symbol='mm',
        cm_to_unit=10.0,
        default_tube_od='44.45',
        default_precision=1,
        valid_precisions=(0, 1, 2, 5, 10),
    )


class TestFormatMetric:
    """Test format_metric() function."""

    # Happy path tests
    def test_format_metric_integer(self) -> None:
        """Integer value with 1 decimal place."""
        assert format_metric(10.0, 1) == "10.0"

    def test_format_metric_one_decimal(self) -> None:
        """Value with one decimal place."""
        assert format_metric(10.5, 1) == "10.5"

    def test_format_metric_two_decimals(self) -> None:
        """Value with two decimal places."""
        assert format_metric(10.55, 2) == "10.55"

    # Defensive: Edge cases
    def test_format_metric_zero(self) -> None:
        """Zero value formats correctly."""
        assert format_metric(0.0, 1) == "0.0"

    def test_format_metric_negative(self) -> None:
        """Negative value formats correctly."""
        assert format_metric(-5.5, 1) == "-5.5"

    def test_format_metric_very_large(self) -> None:
        """Very large value formats correctly."""
        assert format_metric(10000.0, 1) == "10000.0"

    def test_format_metric_very_small(self) -> None:
        """Very small value formats with precision."""
        assert format_metric(0.001, 3) == "0.001"

    # Defensive: Boundary - auto mode (decimal_places=0)
    def test_format_metric_auto_small_value(self) -> None:
        """Auto mode uses 2 decimals for values < 1."""
        assert format_metric(0.55, 0) == "0.55"

    def test_format_metric_auto_medium_value(self) -> None:
        """Auto mode uses 1 decimal for values < 10."""
        # Python uses banker's rounding, so 5.55 rounds to 5.5
        assert format_metric(5.56, 0) == "5.6"

    def test_format_metric_auto_large_value(self) -> None:
        """Auto mode uses 1 decimal for values >= 10."""
        assert format_metric(100.55, 0) == "100.5"

    def test_format_metric_rounds_correctly(self) -> None:
        """Rounding is applied correctly."""
        assert format_metric(10.555, 2) == "10.55"  # Rounds down at .555
        assert format_metric(10.556, 2) == "10.56"  # Rounds up


class TestFormatLength:
    """Test format_length() function."""

    # Happy path - imperial
    def test_format_length_imperial_whole(
        self, imperial_units: UnitConfig
    ) -> None:
        """Imperial whole number with symbol."""
        assert format_length(5.0, 16, imperial_units) == '5"'

    def test_format_length_imperial_fraction(
        self, imperial_units: UnitConfig
    ) -> None:
        """Imperial fractional value with symbol."""
        assert format_length(5.5, 16, imperial_units) == '5 1/2"'

    def test_format_length_imperial_sixteenth(
        self, imperial_units: UnitConfig
    ) -> None:
        """Imperial value with 1/16 precision."""
        assert format_length(5.0625, 16, imperial_units) == '5 1/16"'

    # Happy path - metric
    def test_format_length_metric(self, metric_units: UnitConfig) -> None:
        """Metric value with mm symbol."""
        assert format_length(10.5, 1, metric_units) == "10.5mm"

    def test_format_length_metric_two_decimals(
        self, metric_units: UnitConfig
    ) -> None:
        """Metric value with 2 decimal places."""
        assert format_length(10.55, 2, metric_units) == "10.55mm"

    # Defensive: Edge cases
    def test_format_length_zero_imperial(
        self, imperial_units: UnitConfig
    ) -> None:
        """Zero value in imperial."""
        assert format_length(0.0, 16, imperial_units) == '0"'

    def test_format_length_zero_metric(self, metric_units: UnitConfig) -> None:
        """Zero value in metric."""
        assert format_length(0.0, 1, metric_units) == "0.0mm"

    def test_format_length_negative_imperial(
        self, imperial_units: UnitConfig
    ) -> None:
        """Negative value in imperial."""
        assert format_length(-5.5, 16, imperial_units) == '-5 1/2"'

    def test_format_length_negative_metric(
        self, metric_units: UnitConfig
    ) -> None:
        """Negative value in metric."""
        assert format_length(-10.5, 1, metric_units) == "-10.5mm"

    def test_format_length_very_small_imperial(
        self, imperial_units: UnitConfig
    ) -> None:
        """Very small imperial value rounds to 0."""
        assert format_length(0.001, 16, imperial_units) == '0"'


class TestGetPrecisionLabel:
    """Test get_precision_label() function."""

    # Imperial labels
    def test_precision_label_imperial_16(
        self, imperial_units: UnitConfig
    ) -> None:
        """Standard 1/16 precision label."""
        assert get_precision_label(16, imperial_units) == '1/16"'

    def test_precision_label_imperial_32(
        self, imperial_units: UnitConfig
    ) -> None:
        """1/32 precision label."""
        assert get_precision_label(32, imperial_units) == '1/32"'

    def test_precision_label_imperial_8(
        self, imperial_units: UnitConfig
    ) -> None:
        """1/8 precision label."""
        assert get_precision_label(8, imperial_units) == '1/8"'

    def test_precision_label_imperial_4(
        self, imperial_units: UnitConfig
    ) -> None:
        """1/4 precision label."""
        assert get_precision_label(4, imperial_units) == '1/4"'

    def test_precision_label_imperial_exact(
        self, imperial_units: UnitConfig
    ) -> None:
        """Exact (decimal) mode label."""
        assert get_precision_label(0, imperial_units) == "Exact (decimal)"

    def test_precision_label_imperial_unknown(
        self, imperial_units: UnitConfig
    ) -> None:
        """Unknown precision falls back to fraction format."""
        assert get_precision_label(64, imperial_units) == '1/64"'

    # Metric labels
    def test_precision_label_metric_auto(
        self, metric_units: UnitConfig
    ) -> None:
        """Auto precision for metric."""
        assert get_precision_label(0, metric_units) == "Auto"

    def test_precision_label_metric_1(self, metric_units: UnitConfig) -> None:
        """0.1mm precision label."""
        assert get_precision_label(1, metric_units) == "0.1mm"

    def test_precision_label_metric_2(self, metric_units: UnitConfig) -> None:
        """0.01mm precision label."""
        assert get_precision_label(2, metric_units) == "0.01mm"

    def test_precision_label_metric_other(
        self, metric_units: UnitConfig
    ) -> None:
        """Other decimal places show as description."""
        assert get_precision_label(5, metric_units) == "5 decimal places"


class TestNaNInfGuards:
    """Test NaN and Infinity handling in formatting functions."""

    # format_metric NaN/Inf tests
    def test_format_metric_nan_returns_error(self) -> None:
        """NaN value should return ERROR string."""
        assert format_metric(float('nan'), 2) == "ERROR"

    def test_format_metric_positive_inf_returns_error(self) -> None:
        """Positive infinity should return ERROR string."""
        assert format_metric(float('inf'), 2) == "ERROR"

    def test_format_metric_negative_inf_returns_error(self) -> None:
        """Negative infinity should return ERROR string."""
        assert format_metric(float('-inf'), 2) == "ERROR"

    def test_format_metric_nan_auto_mode_returns_error(self) -> None:
        """NaN value in auto mode (decimal_places=0) should return ERROR."""
        assert format_metric(float('nan'), 0) == "ERROR"

    # decimal_to_fraction (imperial) NaN/Inf tests
    def test_decimal_to_fraction_nan_returns_error(self) -> None:
        """NaN value should return ERROR string."""
        assert decimal_to_fraction(float('nan'), 16) == "ERROR"

    def test_decimal_to_fraction_positive_inf_returns_error(self) -> None:
        """Positive infinity should return ERROR string."""
        assert decimal_to_fraction(float('inf'), 16) == "ERROR"

    def test_decimal_to_fraction_negative_inf_returns_error(self) -> None:
        """Negative infinity should return ERROR string."""
        assert decimal_to_fraction(float('-inf'), 16) == "ERROR"

    def test_decimal_to_fraction_nan_exact_mode_returns_error(self) -> None:
        """NaN value in exact mode (denominator=0) should return ERROR."""
        assert decimal_to_fraction(float('nan'), 0) == "ERROR"

    # format_length integration tests for NaN/Inf
    def test_format_length_metric_nan_returns_error(
        self, metric_units: UnitConfig
    ) -> None:
        """format_length with NaN in metric mode should return ERROR with unit."""
        assert format_length(float('nan'), 1, metric_units) == "ERRORmm"

    def test_format_length_imperial_nan_returns_error(
        self, imperial_units: UnitConfig
    ) -> None:
        """format_length with NaN in imperial mode should return ERROR with unit."""
        assert format_length(float('nan'), 16, imperial_units) == 'ERROR"'
