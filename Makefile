build:
	python3 -m build

clean:
	rm -rf *.egg-info/ build/ dist/

.PHONY: build clean
