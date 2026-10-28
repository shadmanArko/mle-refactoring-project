"""Smoke-test a running instance.

    python scripts/smoke_test.py http://localhost:8000
    python scripts/smoke_test.py http://localhost:8000 --api-key SECRET  # also CRUD

Uses only the standard library so it runs anywhere (CI, a laptop, after a deploy).
Exits non-zero, with a reason, if anything a visitor depends on is broken.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

HOUSE = {
    "bedrooms": 3,
    "bathrooms": 2.0,
    "sqft_living": 1800,
    "grade": 7,
    "zipcode": 98103,
}


def call(
    base: str,
    path: str,
    body: dict | None = None,
    *,
    method: str | None = None,
    api_key: str | None = None,
) -> tuple[int, bytes, dict]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def wait_until_ready(base: str, seconds: int = 120) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if call(base, "/api/health")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit(f"FAIL: {base} was not healthy within {seconds}s")


def run_checks(base: str, api_key: str | None) -> int:
    results: list[bool] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {name} {detail}".rstrip())

    wait_until_ready(base)
    status, body, _ = call(base, "/api/health")
    health = json.loads(body)
    check("health reports a loaded model", status == 200 and health["status"] == "ok")
    check("database reachable", health["database"] == "ok", f"-> {health['database']}")

    answers = HOUSE | {"waterfront": False}
    status, body, _ = call(base, "/api/estimate", answers)
    estimate = json.loads(body) if status == 200 else {}
    sane = status == 200 and estimate["low"] < estimate["estimate"] < estimate["high"]
    check("estimate returns a price and range", sane, f"-> ${estimate.get('estimate')}")

    status, body, _ = call(base, "/api/zipcodes")
    check("zipcodes lists 98103", status == 200 and 98103 in json.loads(body))

    for path in ("/", "/presentation"):
        status, _, headers = call(base, path)
        secure = "content-security-policy" in {k.lower() for k in headers}
        check(f"page {path} loads with security headers", status == 200 and secure)

    status, _, _ = call(base, "/api/estimate", answers | {"grade": 99})
    check("invalid input is rejected with 422", status == 422)

    status, _, _ = call(base, "/api/houses", HOUSE)
    check("anonymous write is refused", status in (401, 403), f"-> {status}")

    if api_key:
        status, body, _ = call(base, "/api/houses", HOUSE, api_key=api_key)
        created = json.loads(body) if status == 201 else {}
        check("create house with key", status == 201, f"-> id {created.get('id')}")
        house_id = created.get("id")
        status, body, _ = call(base, f"/api/houses/{house_id}")
        check("read it back", status == 200 and json.loads(body)["zipcode"] == 98103)
        status, body, _ = call(base, f"/api/houses/{house_id}/estimate")
        check(
            "estimate the stored house",
            status == 200 and json.loads(body)["estimate"] > 0,
        )
        status, _, _ = call(
            base, f"/api/houses/{house_id}", method="DELETE", api_key=api_key
        )
        check("delete it", status == 204, f"-> {status}")
        status, _, _ = call(base, f"/api/houses/{house_id}")
        check("it is gone", status == 404)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("base_url")
    parser.add_argument("--api-key", help="also test create/read/estimate/delete")
    args = parser.parse_args()
    return run_checks(args.base_url, args.api_key)


if __name__ == "__main__":
    raise SystemExit(main())
