"""테스트용 합성 정답 키. 실제 정답 키는 저장소 밖에 있으므로, 공개 문항 정의에 '가짜' 정답을 붙여 서버 전용 데이터를 흉내 낸다.

정답은 문항 id 의 해시로만 정한다(실제 정답과 무관). 수치형은 계산 검증식(check)도 합성 값으로 바꾼다.
"""
import copy
import hashlib
import json
import os

from econova import private_content


def synthetic_full(public):
    full = copy.deepcopy(public)
    for q in full["questions"]:
        h = int(hashlib.sha256(q["id"].encode()).hexdigest(), 16)
        q["explanation"] = f"[합성 해설] {q['id']}"
        if q["type"] == "mcq":
            q["answer"] = q["choices"][h % len(q["choices"])]["id"]
        else:
            q["answer"], q["tolerance"] = 24.0, 0.5
            q["check"] = {"type": "product", "factors": [4, 6], "expected": 24, "answer_field": "expected"}
    return full


def write_synthetic_keys(directory, public, assessment_id=None):
    """public 정의에 맞는 합성 키 파일을 directory 에 쓴다 (테스트 전용 임시 폴더)."""
    aid = assessment_id or public["id"]
    _, keys = private_content.split(synthetic_full(public), aid)
    with open(os.path.join(directory, f"{aid}{private_content.KEYS_SUFFIX}"), "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False)
