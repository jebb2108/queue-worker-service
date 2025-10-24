test:
	PYTHONPATH=. pytest --tb=short

watch-tests:
	PYTHONPATH=. find . -name '*.py' | entr -n pytest --tb=short

black:
	black -l 86 $$(find * -name '*.py')
