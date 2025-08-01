# Use the official AWS Lambda base image for Python 3.11
FROM public.ecr.aws/lambda/python:3.11

# Copy only required files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy handler and source code
COPY lambda_function.py .
COPY src/ ./src

# Set the Lambda function handler
CMD ["lambda_function.lambda_handler"]
