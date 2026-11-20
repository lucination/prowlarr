# Native builds only: GitHub uses separate amd64 and arm64 runners.
FROM node:24-bookworm-slim@sha256:dc26ae92c9fb15cf6b1d63e20f0944b2efe0f115b20e00be48fb23fceb061c54 AS ui
WORKDIR /src
COPY package.json yarn.lock ./
COPY .yarnrc ./
RUN yarn install --frozen-lockfile --network-timeout 120000
COPY frontend frontend
COPY tsconfig.json ./
ENV NODE_OPTIONS=--max-old-space-size=2048
RUN yarn build --env production

FROM mcr.microsoft.com/dotnet/sdk:10.0.404@sha256:bef136a371963aaa46ec97882845ef6f54dec15728bb4b128b1c2a400ffbc9b4 AS backend
WORKDIR /src
COPY global.json ./
COPY .editorconfig ./
COPY src src
COPY azure-pipelines.yml ./
# Dependency also serializes the two memory-intensive source builds.
COPY --from=ui /src/_output/UI /package/bin/UI
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_PROCESSOR_COUNT=2 DOTNET_GCHeapHardLimit=0x80000000 MSBUILDDISABLENODEREUSE=1
# Upstream's three-component version, with an explicit fork build component.
# OCI revision and immutable tags carry the exact commit, not AssemblyVersion.
RUN set -eu; version=$(sed -n "s/.*majorVersion: '\([0-9.]*\)'.*/\1/p" azure-pipelines.yml); \
    test -n "$version"; \
    case "$(uname -m)" in x86_64) rid=linux-x64;; aarch64) rid=linux-arm64;; *) exit 1;; esac; \
    for project in NzbDrone.Console/Prowlarr.Console NzbDrone.Mono/Prowlarr.Mono; do \
      dotnet publish "src/$project.csproj" -c Release -f net10.0 -r "$rid" --self-contained true \
        --maxcpucount:1 -p:UseSharedCompilation=false -p:SolutionDir=/src/src/ \
        -p:RuntimeIdentifiers="$rid" -p:AssemblyVersion="$version.0" -p:AssemblyConfiguration=main \
        -o /package/bin; \
    done; \
    test -s /package/bin/Prowlarr.Mono.dll; test -s /package/bin/libMono.Unix.so; \
    printf 'PackageVersion=%s.0\nPackageAuthor=lucination\nUpdateMethod=Docker\nUpdateMethodMessage=Update the container image to upgrade.\nBranch=master\n' "$version" > /package/package_info

FROM mcr.microsoft.com/dotnet/runtime-deps:10.0@sha256:fabe6d8f15c430642a1f92ba0b8d58ff81370cd34c39a182164ad13ba136d38f AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl sqlite3 && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /config && chown 9696:9696 /config
WORKDIR /app/bin
COPY --from=backend /package /app
COPY LICENSE /app/bin/LICENSE
COPY distribution/docker/healthcheck.sh /app/healthcheck.sh
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/lucination/prowlarr" \
      org.opencontainers.image.revision="$SOURCE_REVISION" \
      org.opencontainers.image.licenses="GPL-3.0-only" \
      org.opencontainers.image.title="Prowlarr (lucination fork)"
USER 9696:9696
VOLUME /config
EXPOSE 9696
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=3 CMD ["/bin/sh", "/app/healthcheck.sh"]
ENTRYPOINT ["/app/bin/Prowlarr", "-nobrowser", "-data=/config"]
