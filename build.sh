#!/bin/bash

# Build script for PMS application with options for AI dependencies

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}PMS Application Build Script${NC}"
echo "=================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

# Parse command line arguments
BUILD_TYPE="full"
SKIP_AI=false
BUILD_TIMEOUT=1800

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-ai)
            SKIP_AI=true
            BUILD_TYPE="no-ai"
            shift
            ;;
        --timeout)
            BUILD_TIMEOUT="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --no-ai     Build without AI/ML dependencies (faster)"
            echo "  --timeout   Set build timeout in seconds (default: 1800)"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}Build Type: ${BUILD_TYPE}${NC}"
echo -e "${YELLOW}Build Timeout: ${BUILD_TIMEOUT}s${NC}"

# Set Dockerfile based on build type
if [ "$SKIP_AI" = true ]; then
    DOCKERFILE="Dockerfile.production.noai"
    echo -e "${GREEN}Building without AI dependencies for faster build...${NC}"
else
    DOCKERFILE="Dockerfile.production"
    echo -e "${GREEN}Building with AI dependencies...${NC}"
fi

# Build the image
echo -e "${YELLOW}Starting Docker build...${NC}"
echo "This may take several minutes, especially with AI dependencies."

# Use BuildKit for better performance
export DOCKER_BUILDKIT=1

# Build with timeout
timeout $BUILD_TIMEOUT docker build \
    --file $DOCKERFILE \
    --tag pms-app:latest \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    .

if [ $? -eq 124 ]; then
    echo -e "${RED}Build timed out after ${BUILD_TIMEOUT} seconds${NC}"
    echo -e "${YELLOW}Try building without AI dependencies using: $0 --no-ai${NC}"
    exit 1
fi

echo -e "${GREEN}Build completed successfully!${NC}"
echo -e "${GREEN}Image tagged as: pms-app:latest${NC}"

# Show image size
IMAGE_SIZE=$(docker images pms-app:latest --format "table {{.Size}}" | tail -n 1)
echo -e "${YELLOW}Image size: ${IMAGE_SIZE}${NC}"

echo -e "${GREEN}You can now run the application with:${NC}"
echo "docker-compose -f docker-compose.production.yml up -d" 