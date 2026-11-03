FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UNEXPECTED_STATE_DIR=/tmp/uneXpected-state

WORKDIR /app

RUN addgroup --system --gid 10001 app && adduser --system --uid 10001 --ingroup app app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY unexpected_runtime ./unexpected_runtime
COPY agent_manifest.json skill_manifest.json ./
COPY skills ./skills
COPY self_improvement ./self_improvement
COPY workflow_profiles ./workflow_profiles
COPY web ./web
COPY migrations ./migrations

RUN python -m compileall -q unexpected_runtime && chown -R app:app /app
USER 10001:10001

EXPOSE 10000
CMD ["python", "-m", "unexpected_runtime.http_api"]
