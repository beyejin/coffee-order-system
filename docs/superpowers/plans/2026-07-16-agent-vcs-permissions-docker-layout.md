# Agent VCS Permissions and Docker Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agent VCS capabilities explicit in the orchestration contract and move the application Dockerfile to `docker/Dockerfile` without changing the build context or runtime services.

**Architecture:** `harness/orchestration-policy.json` remains the machine-readable source of truth, while `docs/ai/orchestration-policy.md` and `harness/README.md` explain the same contract. The implementation role owns product-file changes and local commits; the main orchestrator's provider runtime owns push and merge. Compose keeps the repository root as build context and names `docker/Dockerfile` explicitly.

**Tech Stack:** JSON, Markdown, Python `unittest`, Docker Compose, Gradle/Spring Boot.

## Global Constraints

- Preserve the four fixed role slots: `implementation`, `verification`, `qa`, `pr-review`.
- Keep `implementation` as the only product-file writer and keep reviewers read-only.
- Do not change GitHub token, repository, branch-protection, or operating-system credentials.
- Keep Docker Compose service topology, build context, environment variables, and runtime behavior unchanged.
- All changed paths must remain inside `harness/plans/issue-8-agent-vcs-docker.json` `allowedPaths`.

---

### Task 1: Lock the VCS capability contract with tests

**Files:**
- Modify: `harness/tests/test_orchestration_policy.py:8-141`
- Read: `harness/orchestration-policy.json`

**Interfaces:**
- Consumes: `policy["vcsCapabilities"]` keyed by the four roles and `main-orchestrator`.
- Produces: deterministic assertions for read, product write scope, commit, push, and merge.

- [ ] **Step 1: Add a failing capability-matrix test**

Add a test that expects this exact structure:

```python
expected = {
    "implementation": {
        "read": True,
        "writeProductFiles": True,
        "writeScope": "manifest.allowedPaths",
        "commit": True,
        "push": False,
        "merge": False,
    },
    "verification": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": False,
        "merge": False,
    },
    "qa": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": False,
        "merge": False,
    },
    "pr-review": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": False,
        "merge": False,
    },
    "main-orchestrator": {
        "read": True,
        "writeProductFiles": False,
        "writeScope": "none",
        "commit": False,
        "push": True,
        "merge": True,
    },
}
assert self.policy["vcsCapabilities"] == expected
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `python3 -m unittest discover -s harness/tests -p 'test_orchestration_policy.py'`

Expected: FAIL because `vcsCapabilities` is not present yet.

- [ ] **Step 3: Keep the test focused**

Do not add assertions about GitHub credentials or shell permissions; those are
runtime concerns outside the JSON workflow contract.

### Task 2: Add the policy and human-readable contract

**Files:**
- Modify: `harness/orchestration-policy.json:80-106`
- Modify: `docs/ai/orchestration-policy.md:12-35`
- Modify: `harness/README.md:9-24`

**Interfaces:**
- Consumes: the exact matrix from Task 1.
- Produces: machine-readable `vcsCapabilities` and matching human documentation.

- [ ] **Step 1: Add `vcsCapabilities` after the role definitions**

Use the exact matrix from Task 1 so the test is the executable contract. Keep
`roles[*].writeScope` and `mainOrchestrator.canMerge` unchanged for backward
compatibility.

- [ ] **Step 2: Document the five actors and the credential boundary**

Add a table with columns `actor`, `repo read`, `product file write`, `local commit`,
`branch push`, and `PR merge`. State that the JSON describes workflow capabilities;
actual GitHub credentials remain the final enforcement layer.

- [ ] **Step 3: Link the provider runtime**

In `harness/README.md`, state that `scripts/agent-publish.py` performs the
main-orchestrator push/PR/optional merge path after clean HEAD and evaluate PASS.

- [ ] **Step 4: Run the focused test and confirm it passes**

Run: `python3 -m unittest discover -s harness/tests -p 'test_orchestration_policy.py'`

Expected: PASS with zero failures.

### Task 3: Move Dockerfile and update risk classification

**Files:**
- Delete: `Dockerfile`
- Create: `docker/Dockerfile` with the existing 20-line content unchanged
- Modify: `compose.yaml:32-33,56-57`
- Modify: `harness/risk-policy.json:321-327`

**Interfaces:**
- Consumes: root build context and existing Dockerfile COPY instructions.
- Produces: `docker compose` services that resolve `docker/Dockerfile` explicitly.

- [ ] **Step 1: Move the file without changing its content**

The resulting `docker/Dockerfile` must retain `FROM eclipse-temurin:17-jdk-jammy`,
`WORKDIR /workspace`, root-context `COPY` paths, the builder `bootJar` command,
and the final JRE entrypoint.

- [ ] **Step 2: Make both Compose builds explicit**

Replace each `build: .` with:

```yaml
build:
  context: .
  dockerfile: docker/Dockerfile
```

- [ ] **Step 3: Classify both sides of the rename**

Retain the multi-instance risk pattern `Dockerfile` for rename-source
classification and add `docker/Dockerfile` for the new path. Both paths must
be classified by `multi-instance-runtime`.

- [ ] **Step 4: Validate Compose parsing**

Run: `docker compose config`

Expected: exit code 0 and both `app1` and `app2` resolve
`docker/Dockerfile` with repository root as context.

### Task 4: Run full verification and finalize

**Files:**
- Verify: all changed paths in `harness/plans/issue-8-agent-vcs-docker.json`

**Interfaces:**
- Consumes: the policy, docs, test, Docker, and risk changes from Tasks 1-3.
- Produces: fresh harness evaluation evidence tied to the final commit HEAD.

- [ ] **Step 1: Run formatting and policy checks**

Run:

```bash
python3 -m json.tool harness/orchestration-policy.json
python3 -m json.tool harness/risk-policy.json
python3 -m unittest discover -s harness/tests -p 'test_orchestration_policy.py'
docker compose config
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run the full Gradle suite**

Run: `./gradlew test --console plain`

Expected: `BUILD SUCCESSFUL` and zero failed tests.

- [ ] **Step 3: Run the final harness evaluation**

Run: `python3 scripts/agent-harness.py evaluate harness/plans/issue-8-agent-vcs-docker.json`

Expected: `[PASS]` for scope, risk, contract, harness, Gradle, oracle, and evidence checks.

- [ ] **Step 4: Confirm the final diff**

Run: `git status --short`, `git diff --stat`, and `test ! -e Dockerfile`.

Expected: only manifest-allowed paths are changed, root `Dockerfile` is absent,
and `docker/Dockerfile` exists.

- [ ] **Step 5: Commit the verified change**

```bash
git add Dockerfile docker/Dockerfile compose.yaml harness/README.md \
  harness/orchestration-policy.json harness/plans/issue-8-agent-vcs-docker.json \
  harness/risk-policy.json harness/tests/test_orchestration_policy.py \
  docs/ai/orchestration-policy.md \
  docs/superpowers/specs/2026-07-16-agent-vcs-permissions-docker-layout-design.md \
  docs/superpowers/plans/2026-07-16-agent-vcs-permissions-docker-layout.md
git commit -m "feat: 에이전트 VCS 권한과 Docker 경로 명시"
```

- [ ] **Step 6: Publish only after fresh evaluate PASS**

Run: `python3 scripts/agent-publish.py harness/plans/issue-8-agent-vcs-docker.json`

Expected: the issue branch is pushed and a non-draft Ready for review PR targeting
`main` is created with `Closes #8`.
