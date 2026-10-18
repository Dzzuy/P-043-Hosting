"""python -m eval.copilot_eval {preflight,run,score,report,reconcile}."""

import argparse
import asyncio
from pathlib import Path

from eval.copilot_eval.config import (
    DEFAULT_CALIBRATION,
    DEFAULT_CORPUS,
    DEFAULT_DATASET,
    DEFAULT_MODEL,
    DEFAULT_RUBRIC,
    REPO,
    RunConfig,
)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("preflight", "run", "score", "report", "reconcile"):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        if name == "preflight":
            command.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
            command.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
            command.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
            command.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
            command.add_argument("--judge-model", default=DEFAULT_MODEL)
            command.add_argument("--project")
            command.add_argument("--suite", choices=("benchmark", "development", "repetition"), default="benchmark")
            command.add_argument("--audit", type=Path, required=True)
        if name == "report":
            command.add_argument("--output", type=Path, help="Required outside a closed run")
            command.add_argument("--decisions", type=Path, help="Explicit reviewed decisions; raw scores remain intact")
            command.add_argument(
                "--replay-rrf", action="store_true", help="Replay saved raw ranks with the captured runtime"
            )
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    # Existing runtime relative paths are rooted at the repository.
    import os

    run_dir = args.run_dir.resolve()
    output = args.output.resolve() if args.command == "report" and args.output else None
    decisions = args.decisions.resolve() if args.command == "report" and args.decisions else None
    if args.command == "preflight":
        config = RunConfig(
            run_dir=run_dir,
            project=args.project or run_dir.name,
            dataset=args.dataset,
            corpus=args.corpus,
            rubric=args.rubric,
            calibration=args.calibration,
            judge_model=args.judge_model,
            suite=args.suite,
        )
        audit = args.audit.resolve()
    elif args.command != "report":
        config = RunConfig.load(run_dir)
    os.chdir(REPO)
    if args.command == "preflight":
        from eval.copilot_eval.benchmark_judge import preflight

        asyncio.run(preflight(config, audit))
    elif args.command == "run":
        from eval.copilot_eval.benchmark_run import execute

        asyncio.run(execute(config))
    elif args.command == "score":
        from eval.copilot_eval.benchmark_judge import evaluate

        asyncio.run(evaluate(config))
    elif args.command == "reconcile":
        from eval.copilot_eval.cloud import reconcile_cloud

        reconcile_cloud(config)
    else:
        if args.replay_rrf:
            from eval.copilot_eval.replay import execute

            execute(run_dir)
        from eval.copilot_eval.report import generate

        report = generate(run_dir, output, decisions)
        print(f"Pass {report['case_pass']}; gates {report['release_candidate_pass']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
