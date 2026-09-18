# Build context: backend/ (see infra/template.yaml Metadata.DockerContext)
FROM public.ecr.aws/lambda/python:3.12

COPY recovery_agent/requirements.txt ${LAMBDA_TASK_ROOT}/recovery_agent/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/recovery_agent/requirements.txt

COPY common/ ${LAMBDA_TASK_ROOT}/common/
COPY recovery_agent/ ${LAMBDA_TASK_ROOT}/recovery_agent/

CMD ["recovery_agent.app.handler"]
