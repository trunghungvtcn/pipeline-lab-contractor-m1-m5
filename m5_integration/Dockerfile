# Pin a dated patch tag. Reviewer should re-pin to the current
# `python:3.12.10-slim-bookworm` digest from the registry:
#   crane digest python:3.12.10-slim-bookworm
FROM python:3.12.10-slim-bookworm
WORKDIR /src
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
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
RUN pip install --no-cache-dir --no-index --offline \
    /src/m1_locator /src/m2_asset_store /src/m3_job_ledger /src/m4_notion_projection /src/m5_integration \
    || pip install --no-cache-dir --no-deps \
    /src/m1_locator /src/m2_asset_store /src/m3_job_ledger /src/m4_notion_projection /src/m5_integration
ENV PYTHONPATH=""
CMD ["python", "run_all.py"]
