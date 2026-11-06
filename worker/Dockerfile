# Teacher-labelling worker. The prompt is mounted from a ConfigMap built from
# prompts/teacher_prompt.txt, so the image never drifts from the repository.
FROM python:3.11.10-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PROMPT_PATH=/prompts/teacher_prompt.txt
WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-deps -r requirements.txt
COPY worker/worker.py worker/teacher.py worker/s3util.py ./
USER 10001
CMD ["python", "worker.py"]
