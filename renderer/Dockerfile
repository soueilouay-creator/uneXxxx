# Build from the repository root. Separate one-shot renderer; never deployed as the authenticated API.
FROM mcr.microsoft.com/playwright:v1.63.0-noble
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git build-essential pkg-config yasm nasm libx264-dev python3 && rm -rf /var/lib/apt/lists/*
RUN git init /tmp/ffmpeg-src \
 && git -C /tmp/ffmpeg-src remote add origin https://github.com/FFmpeg/FFmpeg.git \
 && git -C /tmp/ffmpeg-src fetch --depth=1 origin f893221c8d89cb798b829bebe71d55e1a3f242fd \
 && git -C /tmp/ffmpeg-src checkout --detach f893221c8d89cb798b829bebe71d55e1a3f242fd \
 && cd /tmp/ffmpeg-src \
 && ./configure --prefix=/opt/ffmpeg --enable-gpl --enable-libx264 --disable-debug --disable-doc --disable-ffplay \
 && make -j2 && make install \
 && /opt/ffmpeg/bin/ffmpeg -version | grep -F 'ffmpeg version 7.' \
 && rm -rf /tmp/ffmpeg-src
ENV PATH="/opt/ffmpeg/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
RUN git init /opt/lemo-opuscar \
 && git -C /opt/lemo-opuscar remote add origin https://github.com/lemomo-ai/lemo-opuscar.git \
 && git -C /opt/lemo-opuscar fetch --depth=1 origin 5c05490cc55dfb54f8f4c333f0f0e79cb6500564 \
 && git -C /opt/lemo-opuscar checkout --detach 5c05490cc55dfb54f8f4c333f0f0e79cb6500564 \
 && cd /opt/lemo-opuscar && npm ci --omit=dev \
 && test "$(git -C /opt/lemo-opuscar rev-parse HEAD)" = "5c05490cc55dfb54f8f4c333f0f0e79cb6500564" \
 && node -e 'if (Number(process.versions.node.split(".")[0]) < 20) process.exit(1)'
COPY renderer/worker.py /app/worker.py
RUN groupadd --gid 10001 creator && useradd --uid 10001 --gid 10001 --home-dir /tmp/creator --no-create-home --shell /usr/sbin/nologin creator \
 && chmod 0555 /app/worker.py && chown -R root:root /opt/lemo-opuscar /app
ENV LEMO_OPUSCAR_HOME=/opt/lemo-opuscar HOME=/tmp PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PYTHONDONTWRITEBYTECODE=1
WORKDIR /job
USER 10001:10001
ENTRYPOINT ["python3","/app/worker.py"]
