"""Turns the personas in the library into persona pieces, with a review before anything is saved.

    uv run python scripts/extract_persona_pieces.py --dry-run     # look, write nothing
    uv run python scripts/extract_persona_pieces.py               # review each persona, then save
    uv run python scripts/extract_persona_pieces.py --yes         # accept every suggestion that
                                                                  # rejoins exactly, no questions
    uv run --env-file .env.staging python scripts/extract_persona_pieces.py   # against Neon

For each persona it shows the slot suggested for every paragraph. Enter accepts (only when the
pieces would rejoin to the persona's exact text), `4=family 5=work` changes paragraphs,
`names=Full Name|Short` sets the names, `skip` leaves the persona out. The personas themselves
are never changed, and running it again adds nothing that is already in the pool.
"""

import argparse
import asyncio

from jinnverse.db import dispose_engine, get_sessionmaker
from jinnverse.persona_extract import describe, plans_for_all, review, save


async def main(dry_run: bool, yes: bool) -> None:
    async with get_sessionmaker()() as session:
        plans = await plans_for_all(session)
        if dry_run:
            for plan in plans:
                print("\n".join(describe(plan)), end="\n\n")
            exact = sum(plan.rejoins() for plan in plans)
            print(f"{exact} of {len(plans)} personas would rejoin exactly. Nothing was written.")
        else:
            accepted = [
                plan for plan in plans if (plan.rejoins() if yes else review(plan, input, print))
            ]
            report = await save(session, accepted)
            print(
                f"{report.personas} personas: {report.created} pieces created, "
                f"{report.reused} already in the pool."
            )
            if len(accepted) < len(plans):
                print(f"Left out: {len(plans) - len(accepted)} (skipped or not exact).")
    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--dry-run", action="store_true", help="show the plans, write nothing")
    parser.add_argument("--yes", action="store_true", help="accept every exact suggestion")
    options = parser.parse_args()
    asyncio.run(main(options.dry_run, options.yes))
