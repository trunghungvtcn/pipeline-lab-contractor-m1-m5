# linux/amd64 image digest for python:3.12.10-slim-bookworm
# Hub index digest: sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
FROM python:3.12.10-slim-bookworm@sha256:97983fa8cc88343512862c62307159a82261c3528dc025f79e5a3f7af43e50b4
WORKDIR /src
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INDEX=1
COPY vendor/wheels /wheels
COPY requirements.lock /src/requirements.lock
RUN pip install --no-cache-dir --no-index --require-hashes --find-links /wheels -r /src/requirements.lock
COPY m1_locator /src/m1_locator
COPY m2_asset_store /src/m2_asset_store
COPY m3_job_ledger /src/m3_job_ledger
COPY m4_notion_projection /src/m4_notion_projection
COPY m5_integration /src/m5_integration
COPY run_all.py /src/run_all.py
COPY SUPPORT.md /src/SUPPORT.md
RUN pip install --no-cache-dir --no-index --no-build-isolation --no-deps \
    /src/m1_locator \
    /src/m2_asset_store \
    /src/m3_job_ledger \
    /src/m4_notion_projection \
    /src/m5_integration
ENV PYTHONPATH=""
CMD ["python", "run_all.py"]
