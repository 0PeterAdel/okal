PYTHON ?= python3
PYTHONPATH := apps/voice/src

.PHONY: check test compile governance

check: compile test governance

compile:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q apps/voice/src apps/voice/tests

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s apps/voice/tests -v

governance:
	bash scripts/validate-governance.sh
