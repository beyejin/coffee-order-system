#!/usr/bin/env python3
"""실제 저장소 경계를 검증하는 하네스 oracle 실행기."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Sequence


ORACLE_IDS = (
    "oracle.architecture",
    "oracle.api-contract",
    "oracle.migration-fresh",
    "oracle.migration-upgrade",
    "oracle.transaction",
    "oracle.cross-domain-concurrency",
    "oracle.async-isolation",
    "oracle.multi-instance",
)

ORACLE_TESTS = {
    "oracle.api-contract": (
        "com.example.coffee.domain.menu.MenuControllerTest",
        "com.example.coffee.domain.point.PointChargeIntegrationTest",
        "com.example.coffee.domain.order.OrderIntegrationTest",
        "com.example.coffee.domain.ranking.PopularMenuIntegrationTest",
    ),
    "oracle.migration-fresh": ("com.example.coffee.CoffeeApplicationTests",),
    "oracle.migration-upgrade": ("com.example.coffee.MigrationUpgradeTest",),
    "oracle.transaction": (
        "com.example.coffee.domain.point.PointChargeIntegrationTest",
        "com.example.coffee.domain.order.OrderIntegrationTest",
    ),
    "oracle.cross-domain-concurrency": (
        "com.example.coffee.domain.concurrency.CrossDomainConcurrencyIntegrationTest",
    ),
    "oracle.async-isolation": (
        "com.example.coffee.domain.order.OrderAsyncIsolationTest",
    ),
}

JAVA_IMPORT_PATTERN = re.compile(
    r"^\s*import\s+(com\.example\.coffee\.[\w.]+);",
    re.MULTILINE,
)
PACKAGE_PATTERN = re.compile(r"^\s*package\s+([\w.]+);", re.MULTILINE)
CLASS_PATTERN = re.compile(r"\bclass\s+(\w+)")
BASE_MAPPING_PATTERN = re.compile(
    r"@RequestMapping(?:\(\s*(?:path\s*=\s*)?[\"']([^\"']*)[\"']\s*\))?"
)
HTTP_MAPPING_PATTERN = re.compile(
    r"@(Get|Post|Put|Delete|Patch)Mapping"
    r"(?:\(\s*(?:path\s*=\s*)?[\"']([^\"']*)[\"']\s*\))?"
)
MIGRATION_PATTERN = re.compile(r"^V([1-9][0-9]*)__[^/]+\.sql$")


class OracleFailure(RuntimeError):
    """판정 가능한 oracle 실패."""


def _require_file(root: Path, relative_path: str) -> Path:
    path = root / relative_path
    if not path.is_file():
        raise OracleFailure(f"필수 oracle 파일이 없습니다: {relative_path}")
    return path


def _load_json(root: Path, relative_path: str) -> dict[str, object]:
    path = _require_file(root, relative_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OracleFailure(f"{relative_path} JSON을 읽을 수 없습니다: {error}") from error
    if not isinstance(payload, dict):
        raise OracleFailure(f"{relative_path} 최상위 값은 object여야 합니다.")
    return payload


def _layer(package_name: str) -> str:
    prefix = "com.example.coffee."
    if not package_name.startswith(prefix):
        return "external"
    tail = package_name[len(prefix) :].split(".")
    if tail[0] == "domain" and len(tail) >= 2:
        return f"domain.{tail[1]}"
    if tail[0] == "infra" and len(tail) >= 2:
        return f"infra.{tail[1]}"
    return tail[0]


def _layer_matches(actual: str, declared: str) -> bool:
    return actual == declared or actual.startswith(f"{declared}.")


def _find_cycle(edges: Iterable[tuple[str, str]]) -> tuple[str, ...] | None:
    graph: dict[str, set[str]] = {}
    for source, target in edges:
        if source != target:
            graph.setdefault(source, set()).add(target)
            graph.setdefault(target, set())

    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> tuple[str, ...] | None:
        if node in visiting:
            start = path.index(node)
            return tuple(path[start:] + [node])
        if node in visited:
            return None
        visiting.add(node)
        path.append(node)
        for target in sorted(graph.get(node, ())):
            cycle = visit(target)
            if cycle is not None:
                return cycle
        path.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle is not None:
            return cycle
    return None


def validate_architecture(root: Path) -> str:
    contract = _load_json(root, "harness/contracts/architecture.json")
    if contract.get("schemaVersion") != 1:
        raise OracleFailure("architecture contract schemaVersion은 1이어야 합니다.")
    source_root = contract.get("sourceRoot")
    if source_root != "src/main/java":
        raise OracleFailure("architecture contract의 sourceRoot가 올바르지 않습니다.")
    raw_rules = contract.get("forbiddenImports")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise OracleFailure("architecture contract에 forbiddenImports가 없습니다.")
    rules: list[tuple[str, str]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise OracleFailure("architecture contract의 금지 규칙 형식이 올바르지 않습니다.")
        source = raw_rule.get("from")
        target = raw_rule.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            raise OracleFailure("architecture contract의 from/to는 문자열이어야 합니다.")
        rules.append((source, target))

    source_files = sorted((root / source_root).glob("**/*.java"))
    if not source_files:
        raise OracleFailure("architecture oracle이 검사할 Java source를 찾지 못했습니다.")

    edges: set[tuple[str, str]] = set()
    violations: list[str] = []
    for source_file in source_files:
        text = source_file.read_text(encoding="utf-8")
        package_match = PACKAGE_PATTERN.search(text)
        if package_match is None:
            raise OracleFailure(f"package 선언이 없습니다: {source_file.relative_to(root)}")
        source_layer = _layer(package_match.group(1))
        for imported_package in JAVA_IMPORT_PATTERN.findall(text):
            target_layer = _layer(imported_package)
            if target_layer == "external":
                continue
            edges.add((source_layer, target_layer))
            for rule_source, rule_target in rules:
                if _layer_matches(source_layer, rule_source) and _layer_matches(
                    target_layer, rule_target
                ):
                    violations.append(
                        f"{source_file.relative_to(root)}: {source_layer} -> {target_layer}"
                    )

    if violations:
        raise OracleFailure(
            "금지된 package 의존성이 발견되었습니다: " + ", ".join(sorted(violations))
        )
    cycle = _find_cycle(edges)
    if cycle is not None:
        raise OracleFailure("package 의존성 순환이 발견되었습니다: " + " -> ".join(cycle))
    return f"architecture PASS: {len(source_files)}개 Java source, 순환·금지 의존성 없음"


def _join_paths(base: str, suffix: str | None) -> str:
    if not suffix:
        return base or "/"
    if not base:
        return "/" + suffix.lstrip("/")
    return base.rstrip("/") + "/" + suffix.lstrip("/")


def _controller_routes(root: Path) -> list[tuple[str, str, str]]:
    controller_files = sorted((root / "src/main/java").glob("**/controller/*Controller.java"))
    routes: list[tuple[str, str, str]] = []
    for controller_file in controller_files:
        text = controller_file.read_text(encoding="utf-8")
        class_match = CLASS_PATTERN.search(text)
        if class_match is None:
            raise OracleFailure(f"controller class 선언이 없습니다: {controller_file.relative_to(root)}")
        base_match = BASE_MAPPING_PATTERN.search(text)
        base = base_match.group(1) if base_match is not None else ""
        for method, suffix in HTTP_MAPPING_PATTERN.findall(text):
            routes.append((method.upper(), _join_paths(base, suffix or None), class_match.group(1)))
    return routes


def validate_api_contract(root: Path) -> str:
    contract = _load_json(root, "harness/contracts/api-contract.json")
    if contract.get("schemaVersion") != 1:
        raise OracleFailure("API contract schemaVersion은 1이어야 합니다.")
    documentation = contract.get("documentation")
    if not isinstance(documentation, str):
        raise OracleFailure("API contract documentation 경로가 없습니다.")
    documentation_text = _require_file(root, documentation).read_text(encoding="utf-8")
    raw_endpoints = contract.get("endpoints")
    if not isinstance(raw_endpoints, list) or not raw_endpoints:
        raise OracleFailure("API contract endpoints가 비어 있습니다.")
    expected: set[tuple[str, str]] = set()
    expected_controllers: dict[tuple[str, str], str] = {}
    for raw_endpoint in raw_endpoints:
        if not isinstance(raw_endpoint, dict):
            raise OracleFailure("API contract endpoint 형식이 올바르지 않습니다.")
        method = raw_endpoint.get("method")
        path = raw_endpoint.get("path")
        controller = raw_endpoint.get("controller")
        if not all(isinstance(value, str) and value for value in (method, path, controller)):
            raise OracleFailure("API contract endpoint의 method/path/controller가 올바르지 않습니다.")
        key = (method.upper(), path)
        if key in expected:
            raise OracleFailure(f"API contract endpoint가 중복되었습니다: {key}")
        expected.add(key)
        expected_controllers[key] = controller
        if f"{method.upper()} {path}" not in documentation_text:
            raise OracleFailure(f"API 문서에 endpoint가 없습니다: {method.upper()} {path}")

    actual_routes = _controller_routes(root)
    actual = {(method, path) for method, path, _ in actual_routes}
    if actual != expected:
        raise OracleFailure(
            f"controller endpoint와 contract가 다릅니다: actual={sorted(actual)}, expected={sorted(expected)}"
        )
    for method, path, controller in actual_routes:
        if expected_controllers[(method, path)] != controller:
            raise OracleFailure(f"endpoint controller가 다릅니다: {method} {path} -> {controller}")

    response_source = _require_file(root, "src/main/java/com/example/coffee/global/response/ApiResponse.java")
    response_text = response_source.read_text(encoding="utf-8")
    if re.search(
        r"record\s+ApiResponse<[^>]+>\s*\(\s*boolean\s+success\s*,\s*T\s+data\s*,\s*ApiError\s+error",
        response_text,
    ) is None:
        raise OracleFailure("ApiResponse의 success/data/error wrapper가 계약과 다릅니다.")

    handler_text = _require_file(
        root, "src/main/java/com/example/coffee/global/error/GlobalExceptionHandler.java"
    ).read_text(encoding="utf-8")
    if "@RestControllerAdvice" not in handler_text or "ApiResponse.failure" not in handler_text:
        raise OracleFailure("공통 API 오류 wrapper를 처리하는 GlobalExceptionHandler가 없습니다.")

    error_source = _require_file(root, "src/main/java/com/example/coffee/global/error/ErrorCode.java")
    error_text = error_source.read_text(encoding="utf-8")
    raw_errors = contract.get("errorCodes")
    if not isinstance(raw_errors, dict) or not raw_errors:
        raise OracleFailure("API contract errorCodes가 비어 있습니다.")
    for code, status in raw_errors.items():
        if not isinstance(code, str) or not isinstance(status, int):
            raise OracleFailure("API contract errorCodes 형식이 올바르지 않습니다.")
        status_match = re.search(
            rf"\b{re.escape(code)}\(HttpStatus\.([A-Z_]+)", error_text
        )
        if status_match is None:
            raise OracleFailure(f"ErrorCode에 계약된 code가 없습니다: {code}")
        http_status = HTTPStatus.__members__.get(status_match.group(1))
        if http_status is None or http_status.value != status:
            raise OracleFailure(f"ErrorCode status가 계약과 다릅니다: {code}")
        if f"`{code}`" not in documentation_text:
            raise OracleFailure(f"API 문서에 error code가 없습니다: {code}")

    return f"api-contract PASS: {len(expected)}개 endpoint, {len(raw_errors)}개 error code"


def validate_migration_sequence(root: Path) -> str:
    migration_root = root / "src/main/resources/db/migration"
    files = sorted(migration_root.glob("V*.sql"))
    if not files:
        raise OracleFailure("Flyway migration 파일을 찾지 못했습니다.")
    versions: list[int] = []
    for path in files:
        match = MIGRATION_PATTERN.fullmatch(path.name)
        if match is None:
            raise OracleFailure(f"Flyway migration 파일명 형식이 올바르지 않습니다: {path.name}")
        versions.append(int(match.group(1)))
    if len(versions) != len(set(versions)):
        raise OracleFailure("Flyway migration version이 중복되었습니다.")
    expected = list(range(1, max(versions) + 1))
    if sorted(versions) != expected:
        raise OracleFailure(f"Flyway migration version이 연속적이지 않습니다: {sorted(versions)}")
    return f"migration sequence PASS: V1..V{max(versions)}"


def validate_test_sources(root: Path, check_id: str) -> str:
    test_classes = ORACLE_TESTS[check_id]
    for test_class in test_classes:
        relative_path = f"src/test/java/{test_class.replace('.', '/')}.java"
        _require_file(root, relative_path)
    return f"{check_id} test source PASS: {len(test_classes)}개 test class"


def _run_command(
    root: Path,
    command: Sequence[str],
    *,
    environment: dict[str, str] | None = None,
    timeout_seconds: int = 900,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if environment:
        env.update(environment)
    try:
        completed = subprocess.run(
            tuple(command),
            cwd=root,
            capture_output=True,
            check=False,
            env=env,
            shell=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        return 127, f"Could not find a valid Docker environment or command: {error}"
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or b"") + (error.stderr or b"")
        return 124, output.decode("utf-8", errors="replace") + "\ncommand timeout"
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    return completed.returncode, output


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def run_multi_instance_oracle(root: Path) -> int:
    _require_file(root, "compose.yaml")
    _require_file(root, "nginx/default.conf")
    smoke = _require_file(root, "scripts/multi-instance-smoke.sh")
    if not os.access(smoke, os.X_OK):
        raise OracleFailure("multi-instance smoke script에 실행 권한이 없습니다.")

    project = f"coffee-oracle-{os.getpid()}-{int(time.time())}"
    gateway_port = _free_port()
    db_port = _free_port()
    redis_port = _free_port()
    environment = {
        "COMPOSE_PROJECT_NAME": project,
        "GATEWAY_PORT": str(gateway_port),
        "DB_PORT": str(db_port),
        "REDIS_PORT": str(redis_port),
        "GATEWAY_URL": f"http://127.0.0.1:{gateway_port}",
    }
    compose = ("docker", "compose", "-p", project)
    try:
        exit_code, output = _run_command(root, (*compose, "config", "--quiet"), environment=environment)
        print(output, end="")
        if exit_code != 0:
            return exit_code

        exit_code, output = _run_command(
            root,
            (*compose, "up", "-d", "--build", "--wait"),
            environment=environment,
            timeout_seconds=1200,
        )
        print(output, end="")
        if exit_code != 0:
            return exit_code

        exit_code, output = _run_command(
            root,
            ("sh", "scripts/multi-instance-smoke.sh"),
            environment=environment,
            timeout_seconds=300,
        )
        print(output, end="")
        if exit_code != 0:
            return exit_code
        print("ORACLE PASS: oracle.multi-instance")
        return 0
    finally:
        exit_code, output = _run_command(
            root,
            (*compose, "down", "-v", "--remove-orphans"),
            environment=environment,
            timeout_seconds=180,
        )
        print(output, end="")
        if exit_code != 0:
            raise OracleFailure(f"multi-instance cleanup 실패(exit={exit_code})")


def run_oracle(root: Path, check_id: str) -> int:
    if check_id == "oracle.architecture":
        print(validate_architecture(root))
        return 0
    if check_id == "oracle.api-contract":
        print(validate_api_contract(root))
        print(validate_test_sources(root, check_id))
        return 0
    if check_id == "oracle.migration-fresh":
        print(validate_migration_sequence(root))
        print(validate_test_sources(root, check_id))
        return 0
    if check_id in ORACLE_TESTS:
        print(validate_test_sources(root, check_id))
        return 0
    if check_id == "oracle.multi-instance":
        return run_multi_instance_oracle(root)
    raise OracleFailure(f"지원하지 않는 oracle입니다: {check_id}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("check_id", choices=ORACLE_IDS)
    arguments = parser.parse_args(argv)
    try:
        return run_oracle(arguments.root.resolve(strict=True), arguments.check_id)
    except (OSError, OracleFailure) as error:
        print(f"ORACLE FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
