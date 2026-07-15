#!/usr/bin/env python3
"""로컬 Markdown 링크와 루트 AGENTS.md 소스 컨텍스트 커버리지를 검증한다."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".gradle", ".idea", "build"}
SOURCE_SUFFIXES = {".java", ".sql", ".yaml", ".yml"}
LINK_PATTERN = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")


def files_with_suffix(suffix: str) -> list[Path]:
	return sorted(
		path
		for path in ROOT.rglob(f"*{suffix}")
		if not IGNORED_PARTS.intersection(path.relative_to(ROOT).parts)
	)


def local_link_target(raw_target: str) -> str | None:
	target = raw_target.strip()
	if target.startswith("<") and ">" in target:
		target = target[1:target.index(">")]
	else:
		target = target.split(maxsplit=1)[0]

	parsed = urlsplit(target)
	if parsed.scheme or target.startswith("#") or target.startswith("//"):
		return None
	return unquote(parsed.path)


def broken_markdown_links() -> list[str]:
	errors: list[str] = []
	for markdown in files_with_suffix(".md"):
		content = markdown.read_text(encoding="utf-8")
		for match in LINK_PATTERN.finditer(content):
			target = local_link_target(match.group(1))
			if not target:
				continue
			resolved = (markdown.parent / target).resolve()
			if not resolved.exists():
				errors.append(
					f"{markdown.relative_to(ROOT)} -> {match.group(1)}"
				)
	return errors


def source_files_without_context() -> list[str]:
	source_root = ROOT / "src"
	if not source_root.exists():
		return ["src/ 디렉터리가 없습니다."]

	uncovered: list[str] = []
	for source in sorted(path for path in source_root.rglob("*") if path.suffix in SOURCE_SUFFIXES):
		parent = source.parent
		covered = False
		while True:
			if (parent / "AGENTS.md").is_file():
				covered = True
				break
			if parent == ROOT:
				break
			parent = parent.parent
		if not covered:
			uncovered.append(str(source.relative_to(ROOT)))
	return uncovered


def main() -> int:
	broken_links = broken_markdown_links()
	uncovered_sources = source_files_without_context()

	if broken_links:
		print("[FAIL] 존재하지 않는 로컬 Markdown 링크")
		for error in broken_links:
			print(f"- {error}")
	else:
		print("[PASS] 로컬 Markdown 링크")

	if uncovered_sources:
		print("[FAIL] 루트 AGENTS.md 컨텍스트가 없는 src 파일")
		for source in uncovered_sources:
			print(f"- {source}")
	else:
		print("[PASS] 루트 AGENTS.md 소스 컨텍스트 커버리지 100%")

	return 1 if broken_links or uncovered_sources else 0


if __name__ == "__main__":
	sys.exit(main())
