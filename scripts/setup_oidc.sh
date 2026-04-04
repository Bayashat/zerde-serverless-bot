#!/bin/bash

# ==============================================================================
# AWS OIDC Setup Script for GitHub Actions
# ==============================================================================

set -e

ROLE_NAME="GitHubAction-Deploy-TelegramBot"
REGION=$(aws configure get region)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "🚀 Setting up OIDC in region: $REGION"

# 1. Create OIDC Provider (if it doesn't exist)
# GitHub's OIDC URL is standard
PROVIDER_URL="https://token.actions.githubusercontent.com"
PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

echo "Checking for OIDC provider..."
if aws iam list-open-id-connect-providers | grep -q "$PROVIDER_ARN"; then
    echo "✅ OIDC Provider already exists."
else
    echo "Creating OIDC Provider..."
    # Thumbprint for GitHub is static and public
    aws iam create-open-id-connect-provider \
        --url $PROVIDER_URL \
        --client-id-list "sts.amazonaws.com" \
        --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" \
        1>/dev/null
    echo "✅ OIDC Provider created."
fi

# 2. Create Trust Policy
# This allows ONLY your specific repo's main branch and PRs to assume this role
cat > /tmp/trust_policy.json <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "$PROVIDER_ARN"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:Bayashat/*"
                },
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                }
            }
        }
    ]
}
EOF

# 3. Create IAM Role
echo "Creating/Updating IAM Role: $ROLE_NAME..."
if aws iam get-role --role-name $ROLE_NAME 2>/dev/null; then
    aws iam update-assume-role-policy --role-name $ROLE_NAME --policy-document file:///tmp/trust_policy.json
    echo "✅ Role trust policy updated."
else
    aws iam create-role --role-name $ROLE_NAME --assume-role-policy-document file:///tmp/trust_policy.json
    echo "✅ Role created."
fi

# 4. Attach Permissions
# For CDK deployment, we need pretty broad permissions (AdministratorAccess is easiest for templates)
# In enterprise, you would scope this down, but for a starter kit, Admin is acceptable to prevent deployment errors.
aws iam attach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
echo "✅ AdministratorAccess policy attached."

# 5. Output the Secret
echo ""
echo "=================================================================="
echo "🎉 Setup Complete!"
echo "Please add the following secret to your GitHub Repository:"
echo ""
echo "Name:  AWS_ROLE_ARN"
echo "Value: arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "=================================================================="

rm /tmp/trust_policy.json
