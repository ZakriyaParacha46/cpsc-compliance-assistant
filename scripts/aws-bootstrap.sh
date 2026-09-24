#!/usr/bin/env bash
# One-time: create the AWS stack, the DB password, and the GitHub repo variables the pipeline reads.
# Usage: scripts/aws-bootstrap.sh <owner/repo> <budget-email> [create-oidc=true|false]
# Needs: aws CLI logged in (aws sso login / aws configure), gh CLI logged in.
set -euo pipefail

REPO="$1"
EMAIL="$2"
CREATE_OIDC="${3:-true}"
STACK=cpsc-rag
REGION="${AWS_REGION:-us-east-1}"

echo "==> DB password in SSM (/cpsc-rag/db-password)"
if ! aws ssm get-parameter --region "$REGION" --name /cpsc-rag/db-password >/dev/null 2>&1; then
  aws ssm put-parameter --region "$REGION" --name /cpsc-rag/db-password --type SecureString \
    --value "$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)" >/dev/null
  echo "    created"
else
  echo "    exists, keeping"
fi

echo "==> Deploying CloudFormation stack '$STACK' (CloudFront takes ~5-10 min)"
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file "$(dirname "$0")/../infra/bootstrap.yml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides GitHubRepo="$REPO" BudgetEmail="$EMAIL" CreateOIDCProvider="$CREATE_OIDC"

out() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

echo "==> GitHub 'production' environment (deploys allowed from main only)"
gh api -X PUT "repos/$REPO/environments/production" --input - >/dev/null <<'JSON'
{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
JSON
gh api -X POST "repos/$REPO/environments/production/deployment-branch-policies" -f name=main >/dev/null 2>&1 || true

echo "==> Setting GitHub Actions variables on $REPO"
gh variable set AWS_REGION      --repo "$REPO" --body "$REGION"
gh variable set AWS_ROLE_ARN    --repo "$REPO" --body "$(out AwsRoleArn)"
gh variable set ECR_REPOSITORY  --repo "$REPO" --body "$(out EcrRepository)"
gh variable set ARTIFACT_BUCKET --repo "$REPO" --body "$(out ArtifactBucket)"
gh variable set WEB_BUCKET      --repo "$REPO" --body "$(out WebBucket)"
gh variable set CF_DISTRIBUTION_ID --repo "$REPO" --body "$(out DistributionId)"
gh variable set SITE_URL        --repo "$REPO" --body "$(out SiteUrl)"
gh variable set EC2_INSTANCE_ID --repo "$REPO" --body "$(out InstanceId)"

echo "==> Done. Site: $(out SiteUrl)"
echo "    Push to main to deploy. Confirm the AWS Budgets email subscription in your inbox."
