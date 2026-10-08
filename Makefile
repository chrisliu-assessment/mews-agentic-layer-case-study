.PHONY: audit demo calibrate test
audit:
	python3 -m agentic_gate audit
demo:
	python3 -m agentic_gate demo
calibrate:
	python3 -m agentic_gate calibrate
test:
	python3 -m unittest discover -s tests -v
