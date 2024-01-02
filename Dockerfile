FROM python:3.9

# Create and activate the virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Set the working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the source code
COPY src /app/src
COPY token /app/token
COPY tests /app/tests

# Set the entrypoint to Python
ENTRYPOINT ["python"]

# Set the default command
CMD ["src/main.py"]

# CMD ["python", "src/main.py"]
#  docker run -it notion src/main.py -gt