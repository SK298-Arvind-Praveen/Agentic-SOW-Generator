"""Bounded, configurable budgets for architecture work (seconds)."""
import os


def seconds(stage):
    defaults = {'model': 300, 'composition': 300, 'review': 300,
                'render': 300, 'layout': 120}
    default = defaults[stage]
    try:
        return max(10, min(600, float(os.getenv('ARCHITECTURE_' + stage.upper() + '_TIMEOUT_SECONDS', default))))
    except (TypeError, ValueError):
        return default
