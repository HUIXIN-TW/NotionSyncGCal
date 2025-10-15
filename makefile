# Lint: Run Prettier and Black
lint:
	prettier --write .
	black src/ lambda_function.py --line-length 120
	flake8 src/ lambda_function.py --max-line-length 120
