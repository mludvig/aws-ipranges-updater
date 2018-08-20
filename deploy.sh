#!/bin/bash -xeu

PROJECT_NAME="ipranges_updater"
REGION=ap-southeast-2

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

aws --region ${REGION} cloudformation package --template-file template.yaml --output-template-file "${TEMPLATE_PK}" --s3-bucket "${S3_BUCKET}" --s3-prefix "${PROJECT_NAME}"

aws --region ${REGION} cloudformation deploy --template-file "${TEMPLATE_PK}" --stack-name "${STACK_NAME}" --capabilities CAPABILITY_IAM \
	--parameter-override \
		SelectJson='[{"region":"ap-southeast-2","services":["=AMAZON"]}]' \
		${RouteTables:+RouteTables=${RouteTables}} \
		${RtTarget:+RtTarget=${RtTarget}} \
		${SecurityGroups:+SecurityGroups=${SecurityGroups}} \
		${SgIngressPorts:+SgIngressPorts=${SgIngressPorts}} \
		${SgEgressPorts:+SgEgressPorts=${SgEgressPorts}}
