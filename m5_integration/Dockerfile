FROM python:3.12-slim
WORKDIR /src
RUN pip install --no-cache-dir pytest==8.3.4
COPY m1_locator /src/m1_locator
COPY m2_asset_store /src/m2_asset_store
COPY m3_job_ledger /src/m3_job_ledger
COPY m4_notion_projection /src/m4_notion_projection
COPY m5_integration /src/m5_integration
COPY run_all.py /src/run_all.py
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/src/m5_integration/src:/src/m1_locator/src:/src/m2_asset_store/src:/src/m3_job_ledger/src:/src/m4_notion_projection/src
CMD ["python", "run_all.py"]
