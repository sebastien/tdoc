# Make setup
SHELL:=bash
SHELLFLAGS:=-eu -o pipefail -c
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules

PYTHON=python
PATH_SOURCES_PY=src/py
SOURCES_PY:=$(wildcard $(PATH_SOURCES_PY)/*.py $(PATH_SOURCES_PY)/*/*.py $(PATH_SOURCES_PY)/*/*/*.py $(PATH_SOURCES_PY)/*/*/*/*.py)
MODULES_PY:=$(filter-out %/__main__,$(filter-out %/__init__,$(SOURCES_PY:$(PATH_SOURCES_PY)/%.py=%)))
MANIFEST=$(SOURCES_PY) $(wildcard *.py api/*.* AUTHORS* README* LICENSE*)
BUILD_ALL?=
PRODUCT_ALL=MANIFEST
PYTHON_VERSION?=3.11
PYTHON?=python$(PYTHON_VERSION)
FLAKE8?=flake8
BLACK?=black
MYPYC?=mypyc
BANDIT?=bandit
LPYTHON?=lpython
SHEDSKIN?=shedskin
PYANALYZE?=pyanalyze

PYTHON_MODULE=$(notdir $(firstword $(wildcard $(PATH_SOURCES_PY)/*)))

# TODO: Should test the existence of $1
cmd=if [ -z "$$(which '$1' 2> /dev/null)" ]; then echo "ERR: Could not find command $1"; exit 1; fi; $1

include src/mk/defs.mk

all: $(PRODUCT_ALL) $(BUILD_ALL)


build: $(BUILD_ALL)


release: $(PRODUCT_ALL)
	@python setup.py clean sdist register upload

clean:
	@rm -rf build dist MANIFEST ; true

MANIFEST: $(MANIFEST)
	echo $(MANIFEST) | xargs -n1 | sort | uniq > $@

check: lint audit
	@echo "OK"

audit: require-py-bandit
	@$(BANDIT) -r $(PATH_SOURCES_PY)

# NOTE: The compilation seems to create many small modules instead of a big single one
compile-mypyc: require-py-mypyc
	# NOTE: Output is going to be like '$(PYTHON_MODULE)/__init__.cpython-310-x86_64-linux-gnu.so'
	@$(foreach M,$(MODULES_PY),mkdir -p build/$M;)
	env -C build MYPYPATH=$(realpath .)/src/py $(MYPYC) -p $(PYTHON_MODULE)

compile-shedskin: require-py-shedskin
	@mkdir -p dist
	PYTHONPATH=$(PATH_SOURCES_PY):$(PYTHONPATH) $(SHEDSKIN) build -e $(PYTHON_MODULE)

compile-lpython:
	@mkdir -p dist
	$(LPYTHON) $(SOURCES_PY) -I/usr/lib/python/python3.11/site-packages -I/usrc/lib64/python3.11 -o dist/$(PYTHON_MODULE)

lint: lint-flake8
	@

lint-flake8: require-py-flake8
	@$(FLAKE8) --ignore=E1,E203,E302,E401,E501,E741,F821,W $(SOURCES_PY)

lint-pynalyze: require-py-pyanalyze
	@$(PYANALYZE) $(SOURCES_PY)

format: require-py-black
	@$(BLACK) $(SOURCES_PY)

require-py-%:
	@if [ -z "$$(which '$*' 2> /dev/null)" ]; then $(PYTHON) -mpip install --user --upgrade '$*'; fi

print-%:
	$(info $*=$($*))

.PHONY: audit check compile lint format all doc clean check tests

.ONESHELL:

include src/mk/rules.mk
#EOF
