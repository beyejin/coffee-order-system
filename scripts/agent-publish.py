#!/usr/bin/env python3
"""Publish a verified issue branch and optionally merge its PR."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


Command = tuple[str, ...]
Runner = Callable[[Command, Path], subprocess.CompletedProcess[str]]


class PublishError(Exception):
    pass


@dataclass(frozen=True)
class Manifest:
    issue: int
    target_branch: str
    objective: str
    relative_path: str


@dataclass(frozen=True)
class FinalizationResult:
    state: str
    issue: int
    branch: str
    pr_number: int
    pr_url: str
    merged: bool
    issue_closed: bool | None


def run_command(command: Command, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def command_output(
    runner: Runner,
    command: Command,
    root: Path,
    *,
    description: str,
) -> str:
    result = runner(command, root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PublishError(f"{description} 실패: {detail or '알 수 없는 오류'}")
    return result.stdout.strip()


def load_manifest(root: Path, plan_path: Path) -> Manifest:
    candidate = plan_path if plan_path.is_absolute() else root / plan_path
    try:
        resolved = candidate.resolve(strict=True)
        relative_path = resolved.relative_to(root.resolve()).as_posix()
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        issue = payload["issue"]
        target_branch = payload["targetBranch"]
        objective = payload["objective"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise PublishError(f"manifest를 읽을 수 없습니다: {error}") from error

    if type(issue) is not int or issue < 1:
        raise PublishError("manifest issue가 올바르지 않습니다.")
    if not isinstance(target_branch, str) or not target_branch:
        raise PublishError("manifest targetBranch가 올바르지 않습니다.")
    if not isinstance(objective, str) or not objective:
        raise PublishError("manifest objective가 올바르지 않습니다.")

    return Manifest(issue, target_branch, objective, relative_path)


def current_branch_and_head(runner: Runner, root: Path) -> tuple[str, str]:
    branch = command_output(
        runner,
        ("git", "branch", "--show-current"),
        root,
        description="현재 branch 확인",
    )
    head = command_output(
        runner,
        ("git", "rev-parse", "HEAD"),
        root,
        description="현재 HEAD 확인",
    )
    if not branch:
        raise PublishError("detached HEAD에서는 publish할 수 없습니다.")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise PublishError("현재 HEAD SHA가 올바르지 않습니다.")
    return branch, head


def assert_issue_branch(branch: str, issue: int) -> None:
    match = re.match(r"^(?:feature|fix|refactor|docs)/([1-9][0-9]*)-", branch)
    if match is None or int(match.group(1)) != issue:
        raise PublishError(
            f"branch {branch!r}가 issue #{issue} 전용 branch가 아닙니다."
        )


def assert_clean_worktree(runner: Runner, root: Path) -> None:
    status = command_output(
        runner,
        ("git", "status", "--porcelain"),
        root,
        description="worktree 상태 확인",
    )
    if status:
        raise PublishError(
            "publish 전 worktree가 clean해야 합니다: "
            + ", ".join(status.splitlines())
        )


def evaluate_and_read_evidence(
    runner: Runner,
    root: Path,
    plan_path: Path,
    head: str,
) -> dict[str, object]:
    command_output(
        runner,
        (
            sys.executable,
            str(root / "scripts" / "agent-harness.py"),
            "evaluate",
            plan_path.as_posix(),
        ),
        root,
        description="harness evaluate",
    )
    evidence_path = root / "build" / "harness" / "evaluation.json"
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublishError(f"evaluation.json을 읽을 수 없습니다: {error}") from error

    if evidence.get("state") != "PASS":
        raise PublishError(
            "evaluate 결과가 PASS가 아닙니다: "
            f"{evidence.get('state', '<missing>')}"
        )
    if evidence.get("candidateHeadSha") != head:
        raise PublishError("evaluation의 candidate HEAD가 현재 HEAD와 다릅니다.")
    return evidence


def pr_body(manifest: Manifest, evidence: dict[str, object], head: str) -> str:
    return "\n".join(
        (
            "## 변경 목적",
            "",
            f"- 연결 이슈: Closes #{manifest.issue}",
            f"- 해결하려는 문제: {manifest.objective}",
            "",
            "## 하네스 검증",
            "",
            f"- Manifest: `{manifest.relative_path}`",
            "- Evaluate: `PASS`",
            f"- Candidate HEAD: `{head}`",
        )
    )


def parse_pr_list(raw: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as error:
        raise PublishError(f"PR 목록을 해석할 수 없습니다: {error}") from error
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise PublishError("PR 목록 형식이 올바르지 않습니다.")
    return payload


def create_or_prepare_pr(
    runner: Runner,
    root: Path,
    manifest: Manifest,
    branch: str,
    head: str,
    evidence: dict[str, object],
    title: str | None,
) -> tuple[int, str]:
    command_output(
        runner,
        ("git", "push", "--set-upstream", "origin", branch),
        root,
        description="작업 branch push",
    )
    pr_list = parse_pr_list(
        command_output(
            runner,
            (
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--head",
                branch,
                "--base",
                manifest.target_branch,
                "--json",
                "number,url,isDraft,headRefOid,body",
            ),
            root,
            description="현재 PR 조회",
        )
    )
    if len(pr_list) > 1:
        raise PublishError("같은 branch와 base를 가진 open PR이 여러 개입니다.")

    body = pr_body(manifest, evidence, head)
    if not pr_list:
        pr_url = command_output(
            runner,
            (
                "gh",
                "pr",
                "create",
                "--base",
                manifest.target_branch,
                "--head",
                branch,
                "--title",
                title or f"feat: {manifest.objective}",
                "--body",
                body,
            ),
            root,
            description="Ready for review PR 생성",
        )
        match = re.search(r"/pull/([1-9][0-9]*)$", pr_url)
        if match is None:
            raise PublishError(f"PR URL에서 번호를 읽을 수 없습니다: {pr_url}")
        return int(match.group(1)), pr_url

    existing = pr_list[0]
    number = existing.get("number")
    pr_url = existing.get("url")
    remote_head = existing.get("headRefOid")
    if type(number) is not int or not isinstance(pr_url, str):
        raise PublishError("기존 PR metadata가 올바르지 않습니다.")
    if remote_head != head:
        raise PublishError("push 이후 PR head SHA가 현재 HEAD와 다릅니다.")

    existing_body = existing.get("body")
    if not isinstance(existing_body, str) or f"Closes #{manifest.issue}" not in existing_body:
        updated_body = (existing_body or "").rstrip() + f"\n\nCloses #{manifest.issue}\n"
        command_output(
            runner,
            ("gh", "pr", "edit", str(number), "--body", updated_body),
            root,
            description="PR issue 연결 갱신",
        )
    if existing.get("isDraft") is True:
        command_output(
            runner,
            ("gh", "pr", "ready", str(number)),
            root,
            description="Draft PR을 Ready for review로 전환",
        )
    return number, pr_url


def merge_and_verify(
    runner: Runner,
    root: Path,
    manifest: Manifest,
    pr_number: int,
) -> bool:
    command_output(
        runner,
        ("gh", "pr", "checks", str(pr_number), "--watch", "--fail-fast"),
        root,
        description="PR required checks 대기",
    )
    command_output(
        runner,
        ("gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch=false"),
        root,
        description="PR merge",
    )
    pr_state = json.loads(
        command_output(
            runner,
            ("gh", "pr", "view", str(pr_number), "--json", "state,mergedAt"),
            root,
            description="merge 결과 확인",
        )
    )
    if pr_state.get("state") != "MERGED" or not pr_state.get("mergedAt"):
        raise PublishError("PR merge 결과가 MERGED가 아닙니다.")

    issue_state = json.loads(
        command_output(
            runner,
            ("gh", "issue", "view", str(manifest.issue), "--json", "state"),
            root,
            description="Issue 종료 결과 확인",
        )
    )
    if issue_state.get("state") == "OPEN":
        command_output(
            runner,
            (
                "gh",
                "issue",
                "close",
                str(manifest.issue),
                "--comment",
                f"Closed after merging PR #{pr_number}.",
            ),
            root,
            description="Issue 종료",
        )
        issue_state = json.loads(
            command_output(
                runner,
                ("gh", "issue", "view", str(manifest.issue), "--json", "state"),
                root,
                description="Issue 종료 재확인",
            )
        )
    if issue_state.get("state") != "CLOSED":
        raise PublishError(
            f"PR은 merge됐지만 Issue #{manifest.issue}가 닫히지 않았습니다."
        )
    return True


def finalize(
    root: Path,
    plan_path: Path,
    *,
    merge: bool = False,
    title: str | None = None,
    runner: Runner = run_command,
) -> FinalizationResult:
    manifest = load_manifest(root, plan_path)
    branch, head = current_branch_and_head(runner, root)
    assert_issue_branch(branch, manifest.issue)
    assert_clean_worktree(runner, root)
    evidence = evaluate_and_read_evidence(runner, root, plan_path, head)
    pr_number, pr_url = create_or_prepare_pr(
        runner,
        root,
        manifest,
        branch,
        head,
        evidence,
        title,
    )
    if not merge:
        return FinalizationResult(
            "READY_FOR_REVIEW",
            manifest.issue,
            branch,
            pr_number,
            pr_url,
            False,
            None,
        )
    issue_closed = merge_and_verify(runner, root, manifest, pr_number)
    return FinalizationResult(
        "COMPLETED",
        manifest.issue,
        branch,
        pr_number,
        pr_url,
        True,
        issue_closed,
    )


def find_git_root() -> Path:
    result = run_command(("git", "rev-parse", "--show-toplevel"), Path.cwd())
    if result.returncode != 0 or not result.stdout.strip():
        raise PublishError("Git 저장소 루트를 찾을 수 없습니다.")
    return Path(result.stdout.strip()).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-publish.py")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--title")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        root = find_git_root()
        result = finalize(
            root,
            arguments.plan,
            merge=arguments.merge,
            title=arguments.title,
        )
        print(
            f"[{result.state}] issue=#{result.issue} PR=#{result.pr_number} "
            f"{result.pr_url}"
        )
        return 0
    except PublishError as error:
        print(f"[FAIL] publish: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
