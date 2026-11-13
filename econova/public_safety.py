"""공개 저장소에 올리면 안 되는 자료 검사 (커밋 전 점검).

저장소가 공개(public)이므로, Flask 가 파일을 내려주지 않아도 커밋하는 순간 누구나 볼 수 있다. 그래서 커밋하려는 파일에서
다음을 찾는다:
- 정답 키 파일(*.answers.json) — 개발용 합성 키(content/dev_fixtures/private/, "synthetic": true)만 예외
- 정답·허용오차·해설·검증식이 들어 있는 평가 JSON (문항 목록에 answer/tolerance/explanation/check/verify)
  — 테스트용 합성 데이터(최상위 "synthetic": true)만 예외
- 교사용 검토 문서 (표시 문구가 있거나 docs/review/ 아래)
- API 키·서비스 계정 키처럼 보이는 문자열

사용:
    python -m econova.public_safety            # `git add -A` 로 들어갈 파일 전체 (추적 + 무시되지 않은 새 파일)
    python -m econova.public_safety --staged   # 이미 스테이지한 파일만 (pre-commit 훅: tools/git-hooks/pre-commit)
    flask --app app check-public-files [--staged]
문제가 있으면 종료 코드 1. 파일 내용(정답 값)은 출력하지 않고 위치만 알린다.
"""
import json
import os
import re
import subprocess
import sys

from econova import config
from econova.private_content import KEYS_SUFFIX, public_violations

REVIEW_MARKER = "ECONOVA-TEACHER-ONLY: 정답 포함 교사용 문서"
SYNTHETIC_KEY_DIRS = ("content/dev_fixtures/private/",)
TEACHER_ONLY_DIRS = ("docs/review/",)
SECRET_PATTERNS = (
    ("OpenAI API 키", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("개인 키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("서비스 계정 키", re.compile(r'"private_key"\s*:\s*"')),
    ("GitHub 토큰", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
)
SKIP_SECRET_SCAN = ("econova/public_safety.py", "tests/test_private_content.py")   # 검사 규칙 자체·그 테스트


def scan_text(rel, text):
    """파일 하나(저장소 기준 상대 경로, 내용)의 문제 목록. 정답 값은 메시지에 넣지 않는다."""
    rel = rel.replace(os.sep, "/")
    issues = []
    if any(rel.startswith(d) for d in TEACHER_ONLY_DIRS):
        issues.append("교사용 검토 문서 폴더(docs/review/)의 파일은 공개 저장소에 올리지 않습니다.")
    if REVIEW_MARKER in text and rel != "econova/public_safety.py" and not rel.startswith("econova/review_package"):
        issues.append("정답이 들어 있는 교사용 검토 문서입니다.")
    data = None
    if rel.endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
    synthetic = isinstance(data, dict) and data.get("synthetic") is True
    if rel.endswith(KEYS_SUFFIX):
        if not any(rel.startswith(d) for d in SYNTHETIC_KEY_DIRS):
            issues.append("정답 키 파일은 비공개 폴더(ECONOVA_PRIVATE_CONTENT_DIR)에만 둡니다.")
        elif not synthetic:
            issues.append("개발용 키 폴더의 파일인데 \"synthetic\": true 가 없습니다 (실제 정답일 수 있음).")
    elif isinstance(data, dict) and isinstance(data.get("questions"), list) and not synthetic:
        leaked = public_violations(data)
        if leaked:
            issues.append(f"평가 파일에 정답 정보가 있습니다 ({len(leaked)}곳, 예: {leaked[0]}).")
    if rel not in SKIP_SECRET_SCAN:
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append(f"{name}처럼 보이는 문자열이 있습니다.")
    return issues


def candidate_files(root=None, staged=False):
    """검사할 파일 목록(저장소 기준 상대 경로). staged=False 이면 `git add -A` 가 넣을 파일 전체."""
    root = root or config.BASE_DIR
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    else:
        cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    out = subprocess.run(cmd, cwd=root, capture_output=True, check=True).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p)


def _staged_blob(rel, root):
    """스테이지된(인덱스의) 내용. 작업 트리 파일과 다를 수 있다 (git add -p, 스테이지 뒤 수정)."""
    res = subprocess.run(["git", "show", f":{rel}"], cwd=root, capture_output=True)
    return res.stdout if res.returncode == 0 else None


def scan(paths, root=None, staged=False):
    """{상대 경로: [문제]} (문제가 있는 파일만). staged=True 이면 작업 트리가 아니라 인덱스에 스테이지된 내용을 검사한다
    (실제로 커밋될 내용). GIT_INDEX_FILE 환경변수를 따르므로 임시 인덱스로도 점검할 수 있다."""
    root = root or config.BASE_DIR
    found = {}
    for rel in paths:
        if staged:
            raw = _staged_blob(rel, root)
            if raw is None:
                continue
        else:
            path = os.path.join(root, rel)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                raw = f.read()
        if b"\0" in raw[:4096]:
            continue   # 바이너리
        issues = scan_text(rel, raw.decode("utf-8", errors="replace"))
        if issues:
            found[rel] = issues
    return found


def is_ignored_inside_repo(path, root=None):
    """path 가 저장소 안이면 (inside, git 이 무시하는가). 저장소 밖이면 (False, True)."""
    root = os.path.realpath(root or config.BASE_DIR)
    real = os.path.realpath(path)
    if real != root and not real.startswith(root + os.sep):
        return False, True
    res = subprocess.run(["git", "check-ignore", "-q", "--no-index", os.path.relpath(real, root)], cwd=root)
    return True, res.returncode == 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    staged = "--staged" in argv
    paths = [a for a in argv if not a.startswith("--")] or candidate_files(staged=staged)
    found = scan(paths, staged=staged)
    for rel, issues in found.items():
        for issue in issues:
            print(f"[차단] {rel}: {issue}")
    if found:
        print(f"공개 저장소에 올리면 안 되는 내용이 {len(found)}개 파일에 있습니다. 커밋하지 마세요.")
        return 1
    print(f"공개 저장소 점검 통과: {len(paths)}개 파일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
