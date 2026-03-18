from __future__ import annotations

import sys

from pijiang.cli.main import main as cpj_main


def main(argv: list[str] | None = None) -> int:
    args = ["run"]
    if argv:
        args.extend(argv)
    return cpj_main(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
