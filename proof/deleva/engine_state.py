"""AutonomousEngine's own operating state.

Deliberately separate from ``deleva.models.RiskState``. RiskState answers
"what is the position's risk?" -- a fact about the chain. EngineState answers
"what is DELEVA currently doing?" -- a fact about this process. The two must
never be conflated: a HEALTHY position and a STOPPED engine are unrelated
statements.
"""

from __future__ import annotations

from enum import Enum


class EngineState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    EVALUATING = "EVALUATING"
    TRIGGERED = "TRIGGERED"
    SIMULATING = "SIMULATING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    ERROR = "ERROR"
