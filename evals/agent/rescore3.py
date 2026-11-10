"""Re-score saved runs with matcher v3 (``matcher3.py``): ``rescore.py`` unchanged (it is part of v2's frozen
digest), with its matcher module swapped. Output under ``<runs>/<run>-v3/``.

    python -m evals.agent.rescore3 --run tier1 --run gate1 --include-dropped ...
"""

from __future__ import annotations

import sys

from . import matcher3, rescore

rescore.m2 = matcher3  # every matcher call in rescore goes through this module global
_judge_point = rescore.judge_point


def _judge_point_v3(*args, **kwargs):
    return [dict(r, matcher="v3") if "matcher" in r else r for r in _judge_point(*args, **kwargs)]


rescore.judge_point = _judge_point_v3


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not any(a.startswith("--suffix") for a in argv):
        argv.append("--suffix=-v3")
    return rescore.main(argv)


if __name__ == "__main__":
    sys.exit(main())
