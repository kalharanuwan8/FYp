from datetime import date
from typing import Any, Dict, Optional

from app.services.dsm_indicators import build_dsm_profile


class AnalyticsService:
    """
    Analytics for DSM-5 inattention proxies and session reports.
    """

    @staticmethod
    def generate_dsm_summary(student_id: int, target_date: date) -> dict:
        """Legacy helper — returns the multi-signal profile for a lookback window."""
        _ = target_date
        return build_dsm_profile(student_id=student_id, days=7)

    @staticmethod
    def dsm_profile(student_id: int, days: int = 7) -> Dict[str, Any]:
        return build_dsm_profile(student_id=student_id, days=days)
