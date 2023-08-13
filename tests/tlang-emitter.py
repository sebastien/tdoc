from tdoc.parser import parsePath, TLangEmitter, ValueWriter
import os
res = parsePath(os.path.join(os.path.dirname(__file__), "../examples/document.tdoc"), emitter=TLangEmitter(), writer=ValueWriter())
print (res)
# EOF
