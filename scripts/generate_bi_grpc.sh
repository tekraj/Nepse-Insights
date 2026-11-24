#!/usr/bin/env sh
# Regenerates the api-service <-> business-intelligence gRPC stubs from
# nepse-common/nepse_common/bi_grpc/business_intelligence.proto. Run from
# the dev venv (grpcio-tools is in the root pyproject's dev group):
#
#   source .venv/bin/activate && scripts/generate_bi_grpc.sh
#
# The generated files are committed; protoc's version must not be newer
# than the protobuf runtime in the images (the generated code checks it).
set -eu
cd "$(dirname "$0")/../nepse-common"
python -m grpc_tools.protoc -I . \
  --python_out=. --pyi_out=. --grpc_python_out=. \
  nepse_common/bi_grpc/business_intelligence.proto
echo "generated nepse_common/bi_grpc/business_intelligence_pb2{,_grpc}.py"
