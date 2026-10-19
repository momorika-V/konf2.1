PYTHON ?= python3
SRC = src/main.py

.PHONY: run test clean

run:
	$(PYTHON) $(SRC) $(ARGS)

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf src/__pycache__ tests/__pycache__
