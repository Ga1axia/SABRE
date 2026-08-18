from __future__ import annotations

import sys

from core.cli.app import build_parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        result = handler(args)
        return int(result or 0)
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        remedy = getattr(exc, "remedy", "")
        if remedy:
            print(f"  → {remedy}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
