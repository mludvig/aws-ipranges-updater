#!/bin/bash -xeu

PROJECT_NAME="ipranges_updater"

source config.sh	# See config.sh.template

S3_PREFIX="${PROJECT_NAME}"
TEMPLATE_PK="template.packaged.yaml"
STACK_NAME=$(tr A-Z_ a-z- <<< ${PROJECT_NAME})

PYLINT="pylint --output-format=colorized --disable invalid-name,missing-docstring,bad-whitespace,line-too-long"

echo ==== FYI Only ====
${PYLINT} --exit-zero ${PROJECT_NAME}/lambda.py

echo ==== Catching errors ====
${PYLINT} -E ${PROJECT_NAME}/lambda.py
echo "OK: pylint passed"

echo ==== Build and deploy ====
mkdir -p ${PROJECT_NAME}/build
ln -fv ${PROJECT_NAME}/*.py ${PROJECT_NAME}/build/
make build SERVICE=${PROJECT_NAME}

aws cloudformation package --template-file template.yaml --output-template-file "${TEMPLATE_PK}" --s3-bucket "${S3_BUCKET}" --s3-prefix "${PROJECT_NAME}"

aws cloudformation deploy --template-file "${TEMPLATE_PK}" --stack-name "${STACK_NAME}" --capabilities CAPABILITY_IAM \
	--parameter-override \
		SelectJson=${SELECT_JSON} \
		${ROUTE_TABLES:+RouteTables=${ROUTE_TABLES}} \
		${RT_TARGET:+RtTarget=${RT_TARGET}} \
		${SECURITY_GROUPS:+SecurityGroups=${SECURITY_GROUPS}} \
		${SG_INGRESS_PORTS:+SgIngressPorts=${SG_INGRESS_PORTS}} \
		${SG_EGRESS_PORTS:+SgEgressPorts=${SG_EGRESS_PORTS}}

LAMBDA_ARN=$(aws --region ${REGION} cloudformation describe-stacks --stack-name "${STACK_NAME}" | jq -r '.Stacks[0].Outputs[]|select(.OutputKey=="UpdaterFunction").OutputValue')

# This must be done in us-east-1 because that's the SNS topic region!
aws --region us-east-1 cloudformation deploy --template-file template-subscription.yaml --stack-name "${STACK_NAME}-subscription" \
	--parameter-override LambdaFunctionArn=${LAMBDA_ARN} || true
