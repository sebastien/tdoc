from tdoc.parser import Parser, XMLEmitter, RE_ATTR, STR_SQ, STR_DQ
import re


assert re.match(STR_SQ, "''")
assert re.match(STR_SQ, "'singlequoted'")
assert re.match(STR_SQ, "'single quoted'")

assert re.match(STR_DQ, '""')
assert re.match(STR_DQ, '"singlequoted"')
assert re.match(STR_DQ, '"single quoted"')
assert RE_ATTR.match("a=1")
assert RE_ATTR.match("a='1'")
assert RE_ATTR.match('a="1"')
assert RE_ATTR.match('ns:a="1"')

p = Parser()
assert p.matchNode("document")
assert p.matchNode("document svg=http://www.w3.org/2000/svg")
assert p.matchNode("document xmlns:svg=http://www.w3.org/2000/svg")
match = p.matchNode("document a=1 b='2' c=\"3\"")
parsed = p.parseNode(match)

match = p.matchNode('svg:rect x="10" y="10" width="30" height="30" fill="#FF6B6B"')
parsed = p.parseNode(match)
print(parsed)

#
# e = XMLEmitter()
# for atom in p.feed("document xmlns:svg=http://www.w3.org/2000/svg\n", e):
#     print(atom)
# for atom in p.feed("\tsvg:svg width=300 height=100\n", e):
#     print(atom)
#
# for atom in p.feed(
#     '\t\tsvg:rect x="10" y="10" width="30" height="30" fill="#FF6B6B"\n', e
# ):
#     print(atom)

# EOF
