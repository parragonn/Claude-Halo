"""Point d'entrée : `python -m halo` ou la commande `halo`."""

from __future__ import annotations


def main() -> None:
    from halo.app import run

    run()


if __name__ == "__main__":
    main()
