SOURCES_XML=$(wildcard examples/*.tdoc)
BUILD_HTML+=$(patsubst examples/%.xml.tdoc,build/%.html,$(foreach P,$(wildcard examples/*.xml.tdoc),$(if $(wildcard $(patsubst %.xml.tdoc,%.xsl.tdoc,$P)),$P)))
BUILD_ALL+=$(BUILD_HTML)
# EOF
