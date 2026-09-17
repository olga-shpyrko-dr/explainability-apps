"""
Deploy the generic-explainability app (manufacturing RUL) as a DataRobot
Custom Application via the raw REST API (multipart file upload), following
the same pattern used by CustomModelVersion.create_clean() in the SDK.

This is a snapshot of the exact script used to deploy the live app — see
app_result.json (same folder) for the resulting source_id / version_id /
application_id / application_url, and ../../IMPLEMENTATION_PLAN.md Section 6
for the full deployment narrative (including the backend/.env quoting bug
this uncovered and fixed).

Re-running this script is idempotent for the CustomApplicationSource (it
reuses the existing source by name) but NOT for CustomApplication — it will
fail with a 409 if an app with APP_NAME already exists. Delete the existing
CustomApplication first (dr.CustomApplication.get(id).delete()) if you want
to redeploy from scratch, or just call CustomApplicationSource.get(source_id)
+ get the app to update via a different mechanism (e.g. the DataRobot UI's
"replace source version" action) instead of recreating.
"""
import json
import os
import re
import sys
from pathlib import Path

import datarobot as dr
from requests_toolbelt.multipart.encoder import MultipartEncoder

APP_ROOT = Path("/home/notebooks/storage/generic-explainability")
BASE_ENV_ID = "66d07fae0513a1edf18595bb"  # [DataRobot] Python 3.12 Applications Base
APP_NAME = "Manufacturing RUL Explainability"

# Exclude patterns mirroring infra/infra/explainability_app.py EXCLUDE_PATTERNS
EXCLUDE_PATTERNS = [
    re.compile(p) for p in [
        r"metadata\.yaml",
        r".*node_modules/.*",
        r".*\.venv/.*",
        r".*__pycache__/.*",
        r".*\.pytest_cache/.*",
        r".*\.ruff_cache/.*",
        r".*\.mypy_cache/.*",
        r".*\.uv/.*",
        r".*\.DS_Store",
        r".*\.pyc",
        r".*htmlcov/.*",
        r".*\.coverage",
        r".*infra/.*",
        r".*\.git/.*",
        r".*\.datarobot/.*",
        # NOTE: backend/.env IS intentionally included in this deploy (not
        # excluded) — start-app.sh sources it directly, and it carries all
        # our DEPLOYMENT_ID / SCORING_DATASET_ID / config for this app.
        r".*\.prediction_dataset_cache\.json",
        r".*\.batch_output_cache\.csv",
        r".*manufacturing_rul_source/.*",  # large source data, not needed at runtime
        r".*docs/.*\.pdf",
        r".*frontend/node_modules/.*",
        r".*frontend/src/.*",  # only frontend/dist is needed at runtime
        r".*data/manufacturing_rul_scoring_input\.csv",  # already uploaded to AI Catalog
        r".*data/claim_fraud.*\.csv",  # unused fraud example data
    ]
]


def collect_files(root: Path) -> list[tuple[str, str]]:
    """Return [(local_path, target_path_in_app), ...]."""
    result = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(file_path, root).replace(os.path.sep, "/")
            if any(p.match(rel_path) for p in EXCLUDE_PATTERNS):
                continue
            result.append((file_path, rel_path))
    return result


def build_merged_requirements(root: Path) -> str:
    """
    This deploy path uploads files directly via the raw API (bypassing the
    Pulumi/build-app.sh Docker image build step that normally installs
    requirements-runtime.txt and requirements-llm.txt separately). The
    platform only auto-installs requirements.txt before starting the
    container, so merge all three tiers into one file for this deployment.
    """
    parts = []
    for name in ("requirements.txt", "requirements-runtime.txt", "requirements-llm.txt"):
        path = root / name
        if path.exists():
            parts.append(f"# --- from {name} ---")
            parts.append(path.read_text())
    return "\n".join(parts)


def main():
    dr.Client(
        token=os.environ["DATAROBOT_API_TOKEN"],
        endpoint=os.environ["DATAROBOT_ENDPOINT"],
    )
    client = dr.client.get_client()

    dist_index = APP_ROOT / "frontend" / "dist" / "index.html"
    if not dist_index.exists():
        sys.exit(f"ERROR: {dist_index} not found — run npm run build first.")

    files = collect_files(APP_ROOT)

    # Replace requirements.txt with a merged version covering runtime + llm
    # deps too (see build_merged_requirements docstring for why).
    files = [(local, rel) for local, rel in files if rel != "requirements.txt"]
    merged_req_path = "/tmp/opencode/deploy/requirements.merged.txt"
    Path(merged_req_path).write_text(build_merged_requirements(APP_ROOT))
    files.append((merged_req_path, "requirements.txt"))

    # Drop the now-redundant tiered requirement files from the upload (their
    # content is folded into the merged requirements.txt above).
    files = [
        (local, rel) for local, rel in files
        if rel not in ("requirements-runtime.txt", "requirements-llm.txt", "requirements-export.txt")
    ]

    print(f"Collected {len(files)} files to upload.")
    for _, rel in sorted(files)[:20]:
        print("  ", rel)
    if len(files) > 20:
        print(f"  ... and {len(files) - 20} more")

    # 1. Create the CustomApplicationSource (raw API call — the SDK's
    # CustomApplicationSource.create() wrapper fails client-side parsing
    # immediately after creation because latest_version is null before any
    # version exists; work around by reading the id off the raw response).
    print("\nCreating CustomApplicationSource...")
    existing = None
    for item in client.get("customApplicationSources/", params={"limit": 100}).json()["data"]:
        if item["name"] == APP_NAME:
            existing = item
            break
    if existing:
        source_id = existing["id"]
        print(f"Reusing existing source: {source_id}")
    else:
        resp = client.post("customApplicationSources/", data={"name": APP_NAME})
        source_id = resp.json()["id"]
        print(f"Source created: {source_id}")

    # 2. Upload files as a new version (multipart), matching CustomModelVersion._create pattern
    print("\nUploading files as source version (this may take a minute)...")
    upload_fields: list[tuple[str, object]] = []
    open_files = []
    try:
        for local_path, target_path in files:
            f = open(local_path, "rb")
            open_files.append(f)
            upload_fields.append(("file", (os.path.basename(target_path), f)))
            upload_fields.append(("filePath", target_path))

        upload_fields.append(("baseEnvironmentId", BASE_ENV_ID))

        encoder = MultipartEncoder(fields=upload_fields)
        headers = {"Content-Type": encoder.content_type}
        resp = client.request(
            "post",
            f"customApplicationSources/{source_id}/versions/",
            data=encoder,
            headers=headers,
            timeout=(10, 600),
        )
        print("Version upload status:", resp.status_code)
        version_data = resp.json()
        print(json.dumps({k: version_data[k] for k in ("id", "label", "baseEnvironmentId") if k in version_data}, indent=2))
    finally:
        for f in open_files:
            f.close()

    version_id = version_data["id"]

    # 3. Create the CustomApplication from the source (raw API — the SDK's
    # create_application() wrapper hits similar strict-parsing issues as
    # CustomApplicationSource.create() above). Resources (including the
    # /health endpoint path) are passed directly in the creation payload —
    # confirmed working, no separate PATCH needed.
    print("\nCreating CustomApplication (resources: cpu.xlarge, health endpoint /health)...")
    app_payload = {
        "name": APP_NAME,
        "applicationSourceId": source_id,
        "resources": {
            "resourceLabel": "cpu.xlarge",
            "replicas": 1,
            "sessionAffinity": False,
            "serviceWebRequestsOnRootPath": True,
            "healthEndpointPath": "/health",
        },
    }
    resp = client.post("customApplications/", data=app_payload)
    if resp.status_code == 202:
        from datarobot.utils.waiters import wait_for_async_resolution
        location = wait_for_async_resolution(client, resp.headers["Location"])
        app_resp = client.get(location.replace(client.endpoint, "").lstrip("/"))
        app_data = app_resp.json()
    else:
        app_data = resp.json()

    app_id = app_data.get("id")
    app_url = app_data.get("applicationUrl") or app_data.get("application_url")
    app_status = app_data.get("status")

    print(f"\nCustomApplication created: {app_id}")
    print(f"Application URL: {app_url}")
    print(f"Status: {app_status}")

    with open("/tmp/opencode/deploy/app_result.json", "w") as f:
        json.dump({
            "source_id": source_id,
            "version_id": version_id,
            "application_id": app_id,
            "application_url": app_url,
        }, f, indent=2)


if __name__ == "__main__":
    main()
