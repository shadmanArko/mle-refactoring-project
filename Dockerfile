# syntax=docker/dockerfile:1.7
#
# Three stages: build the virtualenv, train the model, assemble a small runtime
# image that holds only the venv and the trained model (no compilers, no dev tools,
# no training data) and runs as an unprivileged user.
#
# Base images are pinned by digest so builds are reproducible; Dependabot proposes
# updates. Build:  docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -t kc-house .

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM python:3.13.17-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first: this layer is rebuilt only when pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --extra api --no-install-project

# Then the project itself, installed as a wheel (nothing from src/ is needed at runtime).
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --extra api --no-editable


FROM builder AS trainer
# The model is trained during the build, from the same code and the hashed dataset,
# so the image always carries a model that matches its code.
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA} \
    PATH="/app/.venv/bin:$PATH"
COPY data/King_County_House_prices_dataset.csv data/
RUN kc-train --data data/King_County_House_prices_dataset.csv \
        --out /artifacts --card /artifacts/model_card.md


FROM python:3.13.17-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS runtime
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KC_MODEL_DIR=/app/artifacts

# Owned by root and read-only to the app user: the process cannot modify its own code.
COPY --from=builder /app/.venv /app/.venv
COPY --from=trainer /artifacts /app/artifacts

USER app
EXPOSE 8000

# Healthy when the model is loaded (the database is reported but not required).
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

# The app logs every request as JSON itself, so uvicorn's plain-text access log is off.
CMD ["uvicorn", "kc_house.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]


# AWS Lambda target: the same image plus the Lambda Web Adapter, which lets the
# unchanged web app answer Lambda events (API Gateway) while it keeps listening on
# port 8000. Build:  docker build --target lambda --platform linux/arm64 .
# (docker compose and a plain `docker build` use the runtime stage above.)
FROM runtime AS lambda
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter@sha256:46d6625e68cbbdd2efab4a20245977664513f13ffef47915b000d431adcea0b4 /lambda-adapter /opt/extensions/lambda-adapter
ENV AWS_LWA_PORT=8000 \
    AWS_LWA_READINESS_CHECK_PATH=/api/health \
    AWS_LWA_ASYNC_INIT=true
