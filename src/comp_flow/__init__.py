"""CompFlow: Enterprise Total Rewards Calibration & Offer Orchestration Microservice."""

from comp_flow.api.app import app, create_app
from comp_flow.core.config import settings

__version__ = "1.0.0"

__all__ = ["app", "create_app", "settings", "__version__"]
