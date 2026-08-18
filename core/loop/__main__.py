"""Cron entry: python -m core.loop <tick|scan|kill|promote|reconcile>"""

from __future__ import annotations

import json
import sys

from core.envfile import load_env
from core.loop.tick import kill_sweep, promote, reconcile_job, scan, tick
from core.paths import Paths, default_home


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "tick"
    paths = Paths(default_home())
    load_env(paths)
    jobs = {
        "tick": tick,
        "scan": scan,
        "kill": kill_sweep,
        "promote": promote,
        "reconcile": reconcile_job,
    }
    fn = jobs.get(cmd)
    if fn is None:
        print(f"unknown loop job {cmd}", file=sys.stderr)
        return 2
    result = fn(paths)
    sys.stdout.write(json.dumps(result, default=str) + "\n")
    return 0 if result.get("error") is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
