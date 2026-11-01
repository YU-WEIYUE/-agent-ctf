FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils file gdb python3 python3-venv python3-pyelftools python3-capstone gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home analyst
USER 10001:10001
WORKDIR /work
CMD ["sleep", "infinity"]
