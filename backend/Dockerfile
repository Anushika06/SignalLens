# SignalLens backend image. One image, two uses:
#   * default CMD: the API with an in-process worker (Render free tier, single process);
#   * aiKart "Try Me Now": the manifest overrides the command with ["signallens", "aikart-run"].
#
# Build:   docker build -t signallens-agent backend
#          docker build --build-arg INSTALL_BROWSER=1 ...          (adds Playwright + Chromium)
#          docker build --build-arg SL_REMOTE_AGENT_URL=https://api.example.com ...  (aiKart image
#          without keys: briefs are delegated to the hosted SignalLens API)
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ARG INSTALL_BROWSER=0
# Baked into the public image, so only ever a URL and, at most, a dedicated low-privilege key.
ARG SL_REMOTE_AGENT_URL=""
ARG SL_REMOTE_AGENT_KEY=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    SL_REMOTE_AGENT_URL=${SL_REMOTE_AGENT_URL} \
    SL_REMOTE_AGENT_KEY=${SL_REMOTE_AGENT_KEY} \
    SL_BRIEF_READER=auto \
    PORT=8000

WORKDIR /app

# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock README.md ./
RUN if [ "$INSTALL_BROWSER" = "1" ]; then EXTRA="--extra browser"; else EXTRA=""; fi \
    && uv sync --frozen --no-dev --no-install-project $EXTRA

COPY alembic.ini ./
COPY migrations ./migrations
COPY signallens ./signallens
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN if [ "$INSTALL_BROWSER" = "1" ]; then EXTRA="--extra browser"; else EXTRA=""; fi \
    && uv sync --frozen --no-dev $EXTRA \
    && if [ "$INSTALL_BROWSER" = "1" ]; then playwright install --with-deps chromium; fi \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh \
    && useradd --create-home --uid 10001 signallens \
    && mkdir -p /aikart \
    && chown -R signallens:signallens /aikart /app \
    && if [ -d /opt/ms-playwright ]; then chown -R signallens:signallens /opt/ms-playwright; fi \
    && rm -rf /root/.cache

USER signallens
EXPOSE 8000

# No ENTRYPOINT: aiKart replaces CMD with ["signallens", "aikart-run"], which must run as-is.
CMD ["docker-entrypoint.sh"]
