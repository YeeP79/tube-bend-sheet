"""Formatting utilities for measurements and display."""

from __future__ import annotations

import math

from ..models.units import UnitConfig


def gcd(a: int, b: int) -> int:
    """Calculate greatest common divisor using Euclidean algorithm."""
    while b:
        a, b = b, a % b
    return a


def decimal_to_fraction(value: float, denominator: int) -> str:
    """
    Convert decimal to fractional string (for imperial units).

    Args:
        value: Decimal value (can be negative)
        denominator: Fraction denominator (16 for 1/16", 8 for 1/8", etc.)
                    Use 0 for exact decimal display

    Returns:
        Formatted string like "3 1/16" or "14" or "3.7890" (if exact)
        Negative values are prefixed with "-"
        Returns "ERROR" if value is NaN or infinity
    """
    # Guard against invalid float values
    if math.isnan(value) or math.isinf(value):
        return "ERROR"

    if denominator == 0:
        return f"{value:.4f}"

    # Handle negative values by recursing with absolute value
    if value < 0:
        result = decimal_to_fraction(-value, denominator)
        # Don't return "-0" for values that round to zero
        return result if result == "0" else f"-{result}"

    total_parts: int = round(value * denominator)
    whole: int = total_parts // denominator
    numerator: int = total_parts % denominator
    
    if numerator == 0:
        return f"{whole}"
    
    common: int = gcd(numerator, denominator)
    num_simplified: int = numerator // common
    denom_simplified: int = denominator // common
    
    if whole == 0:
        return f"{num_simplified}/{denom_simplified}"
    return f"{whole} {num_simplified}/{denom_simplified}"


def format_metric(value: float, decimal_places: int) -> str:
    """
    Format a metric value with appropriate decimal places.

    Args:
        value: Value in metric units
        decimal_places: Number of decimal places (0=auto/smart rounding)

    Returns:
        Formatted string like "10.5" or "100.25"
        Returns "ERROR" if value is NaN or infinity
    """
    # Guard against invalid float values
    if math.isnan(value) or math.isinf(value):
        return "ERROR"

    if decimal_places == 0:
        # Auto mode - use reasonable precision
        if abs(value) < 1:
            return f"{value:.2f}"
        elif abs(value) < 10:
            return f"{value:.1f}"
        else:
            return f"{value:.1f}"
    else:
        return f"{value:.{decimal_places}f}"


def format_length(value: float, precision: int, units: UnitConfig) -> str:
    """
    Format a length value with appropriate unit symbol.
    
    Args:
        value: Value in display units (already converted from cm)
        precision: Precision setting (denominator for imperial, decimal places for metric)
        units: Unit configuration
        
    Returns:
        Formatted string with unit symbol
    """
    if units.is_metric:
        return f"{format_metric(value, precision)}{units.unit_symbol}"
    else:
        return f'{decimal_to_fraction(value, precision)}{units.unit_symbol}'


def get_precision_label(precision: int, units: UnitConfig) -> str:
    """Get human-readable label for precision value."""
    if units.is_metric:
        if precision == 0:
            return 'Auto'
        elif precision == 1:
            return f'0.1{units.unit_symbol}'
        elif precision == 2:
            return f'0.01{units.unit_symbol}'
        else:
            return f'{precision} decimal places'
    else:
        labels: dict[int, str] = {
            0: 'Exact (decimal)',
            4: '1/4"',
            8: '1/8"',
            16: '1/16"',
            32: '1/32"'
        }
        return labels.get(precision, f"1/{precision}\"")
