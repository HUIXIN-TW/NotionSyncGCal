# Use the official AWS Lambda base image for Python 3.11
FROM public.ecr.aws/lambda/python:3.11

# Install runtime dependencies from the uv lockfile
COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --format requirements-txt -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt

# Copy handler and source code
COPY lambda_function.py .
COPY src/ ./src

# Set the Lambda function handler
CMD ["lambda_function.lambda_handler"]
