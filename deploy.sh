#!/bin/bash -xe

PROJECT_NAME="ipranges_updater"
S3_BUCKET="cf-templates-15v0faruy833o-ap-southeast-2"
REGION=ap-southeast-2

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

aws --region ${REGION} cloudformation deploy --template-file "${TEMPLATE_PK}" --stack-name "${STACK_NAME}" --capabilities CAPABILITY_IAM
