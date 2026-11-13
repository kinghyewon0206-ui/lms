"""ECONOVA 첫 화면과, 없앤 이전 LMS 주소가 다시 생기지 않았는지. 두 저장소에서 모두 실행된다."""
import pytest

from tests.conftest import CSRF


def test_index(client):
    html = client.get("/").get_data(as_text=True)
    assert "ECONOVA" in html and "지속가능발전목표(SDG)로 배우는 경제" in html


def test_index_redirects_when_logged_in(logged_in):
    assert logged_in.get("/").headers["Location"].endswith("/dashboard")


@pytest.mark.parametrize("path", ["/legacy", "/legacy/courses", "/course/econ-micro", "/watch/econ-micro", "/curriculum",
                                  "/curriculum/new", "/curriculum/quick", "/curriculum/1", "/_staging/proxy-diagnostics"])
def test_removed_legacy_pages_are_gone(logged_in, path):
    """이전 LMS(대학 공개 강의·AI 커리큘럼)와 임시 확인용 진단 경로는 없앴다 (2026-11 결정)."""
    assert logged_in.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/curriculum/chat", "/curriculum/quick", "/curriculum/1/delete"])
def test_removed_legacy_actions_are_gone(logged_in, path):
    assert logged_in.post(path, data={"csrf_token": CSRF}, headers={"X-CSRF-Token": CSRF}).status_code in (404, 405)


def test_pages_do_not_link_to_the_old_lms(logged_in):
    for path in ("/dashboard", "/courses", "/does-not-exist"):
        html = logged_in.get(path).get_data(as_text=True)
        assert "이전 LMS" not in html and "/legacy" not in html and "/curriculum" not in html
