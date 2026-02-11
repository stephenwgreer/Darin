#!/bin/bash
# Setup script for GitHub Actions CI/CD workflows
# Run this script to configure your repository for automated deployments

set -e  # Exit on error

echo "=========================================="
echo "GitHub Actions CI/CD Setup"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Not in a git repository${NC}"
    exit 1
fi

echo "Current repository: $(git remote get-url origin 2>/dev/null || echo 'No remote configured')"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for required tools
echo "Checking required tools..."

if command_exists gh; then
    echo -e "${GREEN}✓ GitHub CLI (gh) installed${NC}"
else
    echo -e "${YELLOW}⚠ GitHub CLI (gh) not installed${NC}"
    echo "Install: https://cli.github.com/"
fi

if command_exists uv; then
    echo -e "${GREEN}✓ uv installed${NC}"
else
    echo -e "${YELLOW}⚠ uv not installed${NC}"
    echo "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

if command_exists python3; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [[ $(echo "$PYTHON_VERSION >= 3.11" | bc -l) -eq 1 ]]; then
        echo -e "${GREEN}✓ Python $PYTHON_VERSION installed${NC}"
    else
        echo -e "${YELLOW}⚠ Python $PYTHON_VERSION (need ≥3.11)${NC}"
    fi
else
    echo -e "${RED}✗ Python not installed${NC}"
fi

echo ""
echo "=========================================="
echo "Configuration Steps"
echo "=========================================="
echo ""

# Step 1: Branch Protection
echo "Step 1: Branch Protection Rules"
echo "--------------------------------"
echo ""
echo "Configure branch protection for 'claude-redesign' and 'main' branches:"
echo ""
echo "1. Go to: Settings → Branches → Add rule"
echo ""
echo "For 'claude-redesign' branch:"
echo "  ✓ Require pull request before merging"
echo "  ✓ Require approvals (1)"
echo "  ✓ Require status checks: CI Pipeline Complete"
echo ""
echo "For 'main' branch:"
echo "  ✓ Require pull request before merging"
echo "  ✓ Require approvals (2)"
echo "  ✓ Require status checks: CI Pipeline Complete"
echo "  ✓ Do not allow bypassing"
echo ""
read -p "Press Enter when branch protection configured..."

# Step 2: GitHub Environments
echo ""
echo "Step 2: GitHub Environments"
echo "---------------------------"
echo ""
echo "Create two environments:"
echo ""
echo "Staging Environment:"
echo "  Name: staging"
echo "  Deployment branches: claude-redesign"
echo ""
echo "Production Environment:"
echo "  Name: production"
echo "  Required reviewers: [PM, EM, Abbe]"
echo "  Deployment branches: main"
echo ""
echo "Go to: Settings → Environments → New environment"
echo ""
read -p "Press Enter when environments configured..."

# Step 3: Secrets Configuration
echo ""
echo "Step 3: Repository Secrets"
echo "--------------------------"
echo ""
echo "Add the following secrets: Settings → Secrets → Actions"
echo ""
echo "Required (choose deployment platform):"
echo "  STAGING_DEPLOY_KEY"
echo "  PRODUCTION_DEPLOY_KEY"
echo ""
echo "Optional (monitoring):"
echo "  SENTRY_DSN"
echo "  SLACK_WEBHOOK"
echo ""
echo "Platform-specific (if applicable):"
echo "  RAILWAY_TOKEN"
echo "  RENDER_STAGING_HOOK"
echo "  RENDER_PRODUCTION_HOOK"
echo "  HEROKU_API_KEY"
echo ""
read -p "Press Enter when secrets configured..."

# Step 4: Create environment template
echo ""
echo "Step 4: Environment Template"
echo "----------------------------"
echo ""

if [ ! -f ".env.template" ]; then
    echo "Creating .env.template..."
    cat > .env.template << 'EOF'
# Environment Configuration Template
# Copy this to .env and fill in your values

# Environment
ENVIRONMENT=development

# API Keys (Required)
DEEPGRAM_API_KEY=your-deepgram-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here

# Monitoring (Optional)
SENTRY_DSN=
LOG_LEVEL=INFO

# Database (If applicable)
DATABASE_URL=

# Application Settings
DEBUG=true
EOF
    echo -e "${GREEN}✓ Created .env.template${NC}"
else
    echo -e "${GREEN}✓ .env.template already exists${NC}"
fi

# Verify .env is gitignored
if grep -q "^\.env$" .gitignore 2>/dev/null; then
    echo -e "${GREEN}✓ .env is gitignored${NC}"
else
    echo -e "${YELLOW}⚠ Adding .env to .gitignore${NC}"
    echo ".env" >> .gitignore
fi

echo ""

# Step 5: Test CI locally
echo "Step 5: Test CI Locally"
echo "-----------------------"
echo ""
echo "Testing CI checks locally before pushing..."
echo ""

if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    if command_exists uv; then
        uv venv
        source .venv/bin/activate || source .venv/Scripts/activate
        uv pip install -r requirements.txt
        uv pip install ruff mypy pytest pytest-cov

        echo ""
        echo "Running linting..."
        ruff check . || echo -e "${YELLOW}⚠ Linting issues found${NC}"

        echo ""
        echo "Running type checking..."
        mypy . --exclude '.venv' --ignore-missing-imports || echo -e "${YELLOW}⚠ Type errors found${NC}"

        echo ""
        echo "Running tests..."
        pytest tests/ --cov=. --cov-report=term-missing || echo -e "${YELLOW}⚠ Tests failed${NC}"
    else
        echo -e "${YELLOW}⚠ uv not installed, skipping local tests${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No requirements.txt found${NC}"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Commit workflow files:"
echo "   git add .github/"
echo "   git commit -m \"ci: add GitHub Actions workflows\""
echo "   git push origin claude-redesign"
echo ""
echo "2. Create a test PR to verify CI works:"
echo "   git checkout -b test/ci-verification"
echo "   git push origin test/ci-verification"
echo "   gh pr create --base claude-redesign --title \"Test: CI verification\""
echo ""
echo "3. Configure your deployment platform:"
echo "   - Railway: railway init"
echo "   - Render: Create render.yaml"
echo "   - Heroku: heroku create"
echo ""
echo "4. Update workflow files with deployment commands:"
echo "   Edit: .github/workflows/deploy-staging.yml"
echo "   Edit: .github/workflows/deploy-production.yml"
echo ""
echo "5. Test staging deployment:"
echo "   Merge PR to claude-redesign → Watch Actions tab"
echo ""
echo "6. Test production deployment:"
echo "   Create PR to main → Merge → Approve deployment"
echo ""
echo "Documentation:"
echo "  - .github/workflows/README.md"
echo "  - .github/DEPLOYMENT-CHECKLIST.md"
echo ""
echo -e "${GREEN}Happy deploying! 🚀${NC}"
