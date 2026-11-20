#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
export DOTNET_PROCESSOR_COUNT=2
export DOTNET_GCHeapHardLimit=0xC0000000
export MSBUILDDISABLENODEREUSE=1
export PYTHONDONTWRITEBYTECODE=1
python3 .github/scripts/test_upstream_sync.py
python3 .github/scripts/test_image_policy.py
dotnet test src/Prowlarr.Api.V1.Test/Prowlarr.Api.V1.Test.csproj \
  --configuration Release --maxcpucount:1 \
  -p:UseSharedCompilation=false -p:SolutionDir="$PWD/src/" \
  --logger 'console;verbosity=normal'
dotnet test src/NzbDrone.Core.Test/Prowlarr.Core.Test.csproj \
  --configuration Release --maxcpucount:1 \
  -p:UseSharedCompilation=false -p:SolutionDir="$PWD/src/" \
  --filter 'FullyQualifiedName~NzbDrone.Core.Test.Download.' \
  --logger 'console;verbosity=normal'
git diff --check
