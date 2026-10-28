import json
import re
from pathlib import Path

import pytest

from kc_house.api.routers.pages import WEB_DIR

GOLDEN = Path(__file__).parents[1] / "golden" / "baseline_metrics.json"
PAGES = ["index.html", "presentation.html"]


@pytest.mark.parametrize("path", ["/", "/presentation"])
def test_pages_are_served_as_html_with_a_strict_security_policy(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    policy = response.headers["content-security-policy"]
    assert "default-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", ["/", "/presentation"])
def test_pages_answer_head_requests(client, path):
    assert client.head(path).status_code == 200


@pytest.mark.parametrize("name", PAGES)
def test_pages_load_nothing_from_other_websites(name):
    html = (WEB_DIR / name).read_text()

    assert not re.search(r'(?:src|href)\s*=\s*["\']https?://', html)
    assert "@import" not in html


@pytest.mark.parametrize("name", PAGES)
def test_every_element_the_script_looks_up_exists(name):
    html = (WEB_DIR / name).read_text()
    looked_up = set(re.findall(r'(?:\$|getElementById)\(\s*"([\w-]+)"\s*\)', html))
    defined = set(re.findall(r'\bid="([\w-]+)"', html))

    # Error ids are built as `field + "-error"`; they are defined in the markup.
    assert looked_up <= defined, looked_up - defined


def test_the_tester_page_asks_exactly_the_six_questions():
    html = (WEB_DIR / "index.html").read_text()

    for field in ("bedrooms", "bathrooms", "sqft", "zipcode", "waterfront"):
        assert f'id="{field}"' in html
    assert 'name="grade"' in html
    assert 'api("estimate")' in html


def test_the_tester_page_only_offers_grades_the_api_accepts():
    html = (WEB_DIR / "index.html").read_text()
    grades = [int(g) for g in re.findall(r"\{ grade: (\d+),", html)]

    assert grades and all(3 <= grade <= 13 for grade in grades)


def test_the_deck_has_labelled_slides_and_a_way_to_reach_the_tester():
    html = (WEB_DIR / "presentation.html").read_text()
    slides = re.findall(r'<section class="slide" aria-label="([^"]+)"', html)

    assert len(slides) == 13
    assert len(set(slides)) == len(slides)
    assert 'href="."' in html  # "Open the estimator"


def test_the_deck_quotes_the_notebook_score_from_the_frozen_baseline():
    html = (WEB_DIR / "presentation.html").read_text()
    notebook_r2 = json.loads(GOLDEN.read_text())["elastic_test_r2"]

    assert f"{notebook_r2:.4f}" in html
