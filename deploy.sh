#!/bin/bash -eu

PROJECT_NAME="ipranges_updater"

source config.sh	# See config.sh.template

S3_PREFIX="${PROJECT_NAME}"
TEMPLATE_PK=".template.packaged.yaml"
STACK_NAME=$(tr A-Z_ a-z- <<< ${PROJECT_NAME})

PYLINT="pylint"
PYLINT_CMD="${PYLINT} --output-format=colorized --disable invalid-name,missing-docstring,bad-whitespace,line-too-long"

if which ${PYLINT} > /dev/null; then
	echo ==== FYI Only ====
	${PYLINT_CMD} --exit-zero ${PROJECT_NAME}/lambda.py

	echo ==== Catching errors ====
	${PYLINT_CMD} -E ${PROJECT_NAME}/lambda.py
	echo "OK: pylint passed"
else
	echo !!! ${PYLINT} command is not available, skipping checks !!!
fi

echo ==== Build and deploy ====
set -x
aws cloudformation package --template-file template.yaml --output-template-file "${TEMPLATE_PK}" --s3-bucket "${S3_BUCKET}" --s3-prefix "${PROJECT_NAME}"

aws cloudformation deploy --template-file "${TEMPLATE_PK}" --stack-name "${STACK_NAME}" --capabilities CAPABILITY_IAM \
	--parameter-override \
		SelectJson=${SELECT_JSON} \
		${ROUTE_TABLES:+RouteTables=${ROUTE_TABLES}} \
		${RT_TARGET:+RtTarget=${RT_TARGET}} \
		${SECURITY_GROUPS:+SecurityGroups=${SECURITY_GROUPS}} \
		${SG_INGRESS_PORTS:+SgIngressPorts=${SG_INGRESS_PORTS}} \
		${SG_EGRESS_PORTS:+SgEgressPorts=${SG_EGRESS_PORTS}}
