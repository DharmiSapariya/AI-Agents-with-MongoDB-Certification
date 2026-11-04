install:
	cd backend && pip install -e ".[dev]"
test:
	cd backend && pytest -q
run:
	cd backend && uvicorn app.main:app --reload
index:
	python scripts/create_vector_index.py
