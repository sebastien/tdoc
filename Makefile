VERSION=$(shell grep __version__ src/retro/__init__.py | head -n1 | cut -d'"' -f2)
SOURCES_PY=$(wildcard src/py/*.py src/py/*/*.py  src/py/*/*/*.py)
MANIFEST=$(SOURCES_PY) $(wildcard *.py api/*.* AUTHORS* README* LICENSE*)
PRODUCT=MANIFEST

.PHONY: all doc clean check tests

all: $(PRODUCT)

release: $(PRODUCT)
	@hg commit -a -m "Release $(VERSION)" ; true
	@hg tag "$(VERSION)" ; true
	@hg push --all ; true
	@python setup.py clean sdist register upload

clean:
	@rm -rf build dist MANIFEST ; true

MANIFEST: $(MANIFEST)
	echo $(MANIFEST) | xargs -n1 | sort | uniq > $@

#EOF
