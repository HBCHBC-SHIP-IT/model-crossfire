"""Backward-compatible entry point for AgentRelay.

The project was initially published as Model Crossfire.  Keep this wrapper so
old commands such as ``python model_crossfire.py doctor`` continue to work.
"""

from __future__ import annotations

import sys

from agent_relay import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
