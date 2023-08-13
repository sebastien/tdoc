build/%.xsl: examples/%.xsl.tdoc
	mkdir -p $(dir $@)
	tdoc $< > $@

build/%.xml: examples/%.xml.tdoc
	mkdir -p $(dir $@)
	tdoc $< > $@

build/%.html: build/%.xsl  build/%.xml
	$(call cmd,xsltproc) $^ > $@

#EOF
