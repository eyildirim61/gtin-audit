"""gtin-audit: find barcode and packaging errors in product master data."""

__version__ = "0.1.0"

from .checks import RULES, Issue, Record, audit  # noqa: E402
from .gtin import analyze, compute_check_digit, is_valid_gtin  # noqa: E402

__all__ = ["RULES", "Issue", "Record", "audit", "analyze", "compute_check_digit", "is_valid_gtin", "__version__"]
