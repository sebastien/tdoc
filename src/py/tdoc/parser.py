#!/usr/bin/env python3.8
from tlang import tree
import re, sys, os, logging, json, xml.sax.saxutils
from typing import Optional,Any,List,Union,Iterable,Iterator,Tuple
from enum import Enum
from collections import OrderedDict,namedtuple

# TODO: The parser should yield its position (line, column) and a value
# being either Skip, string, Warning, or Error

# TODO: In embedded, empty elemnts might popup inbetween comments, so
# we should put an option to strip them.

# TODO: The option to wrap the result in a tag, for instance in XML 
# documents.

# TODO: Options

# TODO: Whitespace:
# - preserve: as-is (EOL between tags)
# - normalize: all become spaces

# -----------------------------------------------------------------------------
#
# PARSER
#
# -----------------------------------------------------------------------------

ParseOption = namedtuple("ParseOption", ("type", "default", "help"))
IndentMode  = Enum("IndentMode", ("TABS", "SPACES"))

class ParseOptions:
	"""Define options for parsers, readers and writers."""

	TABS   = "tabs"
	SPACES = "spaces"

	RESERVED = ("OPTIONS", "options", "indentPrefix")

	OPTIONS = {
		"document"   : ParseOption(bool         , False, "Wraps the result in a document node"),
		"comments"   : ParseOption(bool         , False, "Includes comments in the output"),
		"embed"      : ParseOption(bool         , False, "Turns on embedded mode"),
		"embedLine"  : ParseOption(Optional[str], None , "Line prefix for embedded TDoc data (eg. '#')"),
		"embedStart" : ParseOption(Optional[str], None , "Start of embedded TDoc data (eg. '/*')"),
		"embedEnd"   : ParseOption(Optional[str], None , "End of embedded TDoc data (eg. '*/')"),
	}

	def __init__( self, options=None ):
		self.options     = {"indentPrefix":""}
		self.merge(options)

	@property
	def isEmbedded( self ):
		return self.embed or self.embedLine or self.embedStart or self.embedEnd

	def merge( self, options ):
		if options:
			for k,v in options.items():
				if k in self.OPTIONS:
					setattr(self, k, v)
		return self

	def __getattr__( self, name ):
		if name in ParseOptions.RESERVED:
			return object.__getattribute__(self, name)
		elif name not in self.OPTIONS:
			raise ValueError(f"No option {name}, pick any of {tuple(self.OPTIONS.keys())}")
		else:
			return self.options[name] if name in self.options else self.OPTIONS[name]

	def __setattr__( self, name, value ):
		if name in ParseOptions.RESERVED:
			object.__setattr__(self, name, value)
		elif name not in self.OPTIONS:
			raise ValueError(f"No option {name}, pick any of {tuple(self.OPTIONS.keys())}")
		else:
			expected_type = self.OPTIONS[name][0]
			# FIXME: We should test using generics
			if False and not isinstance(value, expected_type):
				raise ValueError(f"Option {name} should be {expected_type}, got {type(value)}: {value}")
			else:
				self.options[name] = value

	def __repr__( self ):
		return repr(self.options)

class ParseError:
	"""Define a parse error, that can be relayed by the writer."""

	def __init__( self, line:int, char:int, message:str, length:int=0 ):
		self.line = line
		self.char = char
		self.message = message
		self.length = length

	def __str__( self ):
		return f"Syntax error at {self.line}:{self.char}: {self.message}"

ParseResult = Union[None,ParseError,str]

# TODO: The parser should have a stack
class Parser:
	"""The TDoc parser is implemented as a straightforward line-by-line
	parser with an event-based (SAX-like) interface.

	The parser uses iterable consistently as an abstraction over multiple
	sources and makes it possible to pause/resume parsing.
	"""

	StackItem    = namedtuple("StackItem", ("depth", "ns", "name"))
	DATA_NODE    = 1
	DATA_ATTR    = 2
	DATA_CONTENT = 3
	DATA_RAW     = 4

	NAME    = "[A-Za-z0-9\-_]+"
	STR_SQ  = "'(\\'|[^'])+'"
	STR_DQ  = '"(\\"|[^"])+"'
	# A value is either a quoted string or a sequence without spaces
	VALUE   = f"({STR_SQ}|{STR_DQ}|[^ ]+)"
	INLINE_ATTR  = f"{NAME}={VALUE}"
	# Attributes are like NAME=VALUE
	# FIXME: Not sure where this is used, might be a @attr name=value
	RE_ATTR = re.compile(f" ((?P<ns>{NAME}):)?(?P<name>{NAME})=(?P<value>{VALUE})?")
	# Nods are like NS:NAME|PARSER ATTR=VALUE: CONTENT
	RE_NODE = re.compile(f"^((?P<ns>{NAME}):)?(?P<name>{NAME})(\#(?P<id>{NAME}))?(\|(?P<parser>{NAME}))?(?P<attrs>( {INLINE_ATTR})*)?(: (?P<content>.*))?$")

	def __init__( self, options:ParseOptions ):
		# TODO: These should be moved into the stack
		self.customParser:Optional[str] = None
		self.customParserDepth:Optional[int] = None
		self.options = options
		self.setIndent(IndentMode.TABS, 1)
		self.stack:List[Parser.StackItem] = []

	def setIndent( self, mode:IndentMode, count:int=1 ):
		"""Sets the indentation level for the parser. This updates the
		indentation prefix that is used to extract indentation from the parsed
		lines."""
		self._indentMode  = mode
		self._indentCount = count
		self._indentPrefix = ('\t' if mode == IndentMode.TABS else ' ') * count
		self.options.indentPrefix = self._indentPrefix

	@property
	def depth( self ):
		return self.stack[-1].depth if self.stack else 0

	def parse( self, iterable:Iterable[str], driver:"Emitter" ):
		"""Parses the given iterable strings, using the given driver to produce
		a result.

		This is equivalent to a combination of `start()`, `feed()` and `end()`,
		and is the preferred method to interact with a parser."""
		yield from self.start(driver)
		for line in iterable:
			yield from self.feed(line, driver)
		yield from self.end(driver)

	def start( self, driver:"Emitter" ):
		"""The parser is stateful, and `start` initializes its state."""
		self.customParser = None
		self.customParserDepth = None
		self.stack = []
		yield from driver.onDocumentStart(self.options)
		if self.options.document:
			yield from driver.onNodeStart(None, self.options.document, None)

	def end( self, driver:"Emitter"  ):
		"""Denotes the end of the parsing."""
		while self.stack:
			d = self.stack.pop()
			yield from driver.onNodeEnd(d.ns, d.name, None)
		if self.options.document:
			yield from driver.onNodeEnd(None, self.options.document, None)
		yield from driver.onDocumentEnd()

	def feed( self, line:str, driver:"Emitter"  ):
		"""Freeds a line into the parser, which produces a directive for
		the driver and may affect the state of the parser."""
		# We get the line indentation, store it as `i`
		i, l = self.getLineIndentation(line)
		# NOTE: We use stopped as a way to exit the loop early, as we're
		# using an iterator.
		stopped = False
		# --- CUSTOM PARSER ---
		if self.customParser:
			# If we have CUSTOM PARSER, then we're going to feed RAW LINES
			if i > self.customParserDepth:
				# BRANCH: RAW_CONTENT
				# That's a nested line, with an indentation greater than
				# the indentation of the custom parser
				yield from driver.onRawContentLine(self.stripLineIndentation(line[:-1], self.customParserDepth + 1))
				stopped = True
			elif not l:
				# BRANCH: RAW_CONTENT_EMPTY
				# This is an empty line, so we log it as an EOL
				yield from driver.onRawContentLine("")
			else:
				# Otherwise, we're OUT of the custom parser
				self.customParser = None
				self.customParserDepth = None
		# --- NOT WITHIN CUSTOM PARSER ---
		if stopped:
			pass
		elif self.isComment(l):
			# BRANCH: COMMENT
			# It's a COMMENT
			yield from driver.onCommentLine(l[1:-1], i)
		elif self.isAttribute(l):
			# BRANCH: ATTRIBUTE
			# It's an ATTRIBUTE
			ns, name, value = self.parseAttributeLine(l[:-1])
			yield from self.onAttribute(driver, ns, name, value)
		elif m := self.isNode(l):
			# If is a node only if it's not too indented. If it is too
			# indented, it's a text.
			if i > self.depth + 1:
				# BRANCH: TEXT CONTENT
				# The current line is TOO INDENTED (more than expected), so we consider
				# it to be TEXT CONTENT
				yield from driver.onContentLine(l[:-1])
			else:
				# BRANCH: TEXT NODE
				# Here we're sure it's a NODE
				if i <= self.depth:
					# If it's DEDENTED, we need to pop the stack up until we
					# reach a depth that's lower than i.
					while self.stack and self.depth >= i:
						d = self.stack.pop()
						# STEP: END PREVIOUS NODE
						yield from driver.onNodeEnd(d.ns, d.name, None)
				else:
					# Here, the indentation must be stricly one more level
					# up.
					assert i == self.depth + 1
				# We parse the node line
				ns, name, parser, attr, content = self.parseNodeLine(l, m)
				self.stack.append(Parser.StackItem(i, ns, name))
				if parser:
					self.customParser = m["parser"]
					self.customParserDepth = i
				# Now we have the node start
				yield from driver.onNodeStart(ns, name, parser)
				# Followed by the attributes, if any
				attr = list(attr)
				for ns, name, value in attr:
					yield from self.onAttribute(driver, ns, name, value)
				yield from driver.onNodeContentStart(ns, name, parser)
				# And then the first line of content, if any
				if content is not None:
					yield from driver.onContentLine(content)
		elif self.isExplicitContent(l):
			yield from driver.onContentLine(l[1:-1])
		else:
			# FIXME: See feature-whitespace, there's a problem there
			text = self.stripLineIndentation(line,self.depth)[:-1]
			if text:
				yield from driver.onContentLine(text)

	# =========================================================================
	# PREDICATES
	# =========================================================================

	def isComment( self, line:str ) -> bool:
		"Tells if the given line is a COMMENT line."""
		return line and line[0] == "#"

	def isExplicitContent( self, line:str ) -> bool:
		"Tells if the given line is an EXPLICIT CONTENT line."""
		return line and line[0] == ":"

	def isNode( self, line:str ) -> bool:
		"""Tells if this line is node line"""
		return self.RE_NODE.match(line)

	def isAttribute( self, line:str ) -> bool:
		"""Tells if this line is attribute line"""
		return line and line[0] == '@'

	# =========================================================================
	# HANDLERS
	# =========================================================================

	def onAttribute( self, driver, ns:str, name:str, value:Any ):
		if ns == "tdoc" and name == "indent":
			v = dict( (k,v) for ns,k,v in self.parseAttributes(" " + value))
			if "spaces" in v:
				self.setIndent(IndentMode.SPACES, int(v.get("spaces",4)))
			elif "tabs" in v:
				self.setIndent(IndentMode.TABS, int(v.get("tabs", 1)))
			else:
				raise SyntaxError(f"tdoc:indent expects `tabs` or `spaces=N` as value, got: `{value}`")
		else:
			yield from driver.onAttribute(ns, name, value)

	# =========================================================================
	# SPECIFIC PARSERS
	# =========================================================================

	def parseNodeLine( self, line, match) -> Tuple[str,str,str,Iterator[Tuple[str,str]],str]:
		attrs = (_ for _ in self.parseAttributes(match.group("attrs")))
		nid   = match.group("id")
		if nid:
			l = [(None, "id", nid)]
			for _ in list(attrs):
				if _[1] == "id" and _[0] is None:
					# TODO: We might want to issue a warning there
					l[0] = _
				else:
					l.append(_)
			attrs = l
		return (
			match.group("ns"),
			match.group("name"),
			match.group("parser"),
			attrs,
			match.group("content"),
		)

	def parseAttributes( self, line:str ) -> Iterator[Tuple[str,str]]:
		"""Parses the attributes and returns a stream of `(key,value)` pairs."""
		# We remove the trailing spaces.
		while line and line[-1] in '\n \t': line = line[:-1]
		# Inline attributes are like
		#   ATTR=VALUE ATTR=VALUE…
		# Where value can be unquoted, single quoted or double quoted,
		# with \" or \' to escape quotes.
		n = len(line)
		o = 0
		while m := self.RE_ATTR.match(line, o):
			v = m.group("value")
			if not v:
				w = v
			# This little dance corrects the string escaping
			elif len(v) < 2:
				w = v
			else:
				s = v[0]
				e = v[-1]
				if s != e:
					w = v
				elif s == '"':
					w = v[1:-1].replace('\\"', '"')
				elif s == "'":
					w = v[1:-1].replace("\\'", "'")
				else:
					w = v
			yield (m.group("ns"), m.group("name"), w or "")
			o = m.end()

	def parseAttributeLine( self, line ):
		# Attributes are like
		#   @NAME VALUE
		# or
		#   @NS:NAME VALUE
		name_value = line.split(' ', 1)
		name         = name_value[0][1:]
		ns_name      = name.split(':', 1)
		if len(ns_name) == 1:
			ns = None
		else:
			ns, name = ns_name
		content = name_value[1] if len(name_value) == 2 else None
		return (ns, name, content)

	# =========================================================================
	# INDENTATION
	# =========================================================================
	# FIXME: This should be reworked and rethought, because many different
	# types of indentation can exist.

	def getLineIndentation( self, line:str ) -> Tuple[int,str]:
		"""Returns the indentation for the line and the non-indented part of
		the line."""
		# TODO: We should support other indentation methods
		n = len(line)
		i = 0 # The indent level
		o = 0 # The character offset
		while o < n and line.startswith(self._indentPrefix, o):
			i += 1
			o += len(self._indentPrefix)
		l = line[o:] if o>0 else line
		return i, l

	def stripLineIndentation( self, line:str, indent:int ) -> str:
		"""Strips the indentation from the given line."""
		n = len(self._indentPrefix)
		while indent >= 0 and line.startswith(self._indentPrefix):
			line = line[n:]
			indent -= 1
		return line

# -----------------------------------------------------------------------------
#
# EMITTER
#
# -----------------------------------------------------------------------------

class Emitter:
	"""An abstract interface for the parser driver. The driver yields
	values that are then handled by a writer. In other words, it transforms
	the stream of events produced by the parser in a stream of values to
	be written."""

	@classmethod
	def GetDefault( cls ):
		return XMLEmitter()

	def __init__( self ):
		self.options = None

	def onDocumentStart( self, options:ParseOptions ):
		self.options = options
		yield None

	def onDocumentEnd( self ):
		yield None

	def onNodeStart( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield None

	def onNodeContentStart( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield None

	def onNodeEnd( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield None

	def onAttribute( self, ns:Optional[str], name:str, value:Optional[str] ):
		yield None

	def onContentLine( self, text:str ):
		yield None

	def onRawContentLine( self, text:str ):
		yield None

	def onCommentLine( self, text:str, indent:int ):
		yield None

# -----------------------------------------------------------------------------
#
# EVENT DRIVER
#
# -----------------------------------------------------------------------------

class EventEmitter(Emitter):
	"""A driver that outputs an event stream."""

	def __init__( self ):
		self.options = None

	def onDocumentStart( self, options:ParseOptions ):
		self.options = options
		yield ('DocumentStart',)

	def onDocumentEnd( self ):
		yield ('DocumentEnd',)

	def onNodeStart( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield ('NodeStart', ns, name, process)

	def onNodeEnd( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield ('NodeEnd', ns, name, process)

	def onAttribute( self, ns:Optional[str], name:str, value:Optional[str] ):
		yield ('Attribute',ns,name,value)

	def onContentLine( self, text:str ):
		yield ('Content',text)

	def onRawContentLine( self, text:str ):
		yield ('RawContent',text)

	def onCommentLine( self, text:str, indent:int ):
		yield ('Comment',text)

# -----------------------------------------------------------------------------
#
# TDOC DRIVER
#
# -----------------------------------------------------------------------------

# FIXME: Deal with empty lines
class TDocEmitter(Emitter):
	"""A driver that outputs a normalized TDoc document."""

	RE_QUOTE = re.compile("[\" ]")

	def __init__( self ):
		self.options = None
		self.indent  = ''
		self.attrIndex = 0

	def onDocumentStart( self, options:ParseOptions ):
		self.options = options
		yield None

	def onDocumentEnd( self ):
		yield None

	def onNodeStart( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield f"{self.indent}{ns+':' if ns else ''}{name}{'|'+process if process else ''}"
		self.indent += '\t'
		self.attrIndex = 0

	def onNodeContentStart( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield '\n'

	def onNodeEnd( self, ns:Optional[str], name:str, process:Optional[str] ):
		self.indent = self.indent[:-1]
		yield None

	def onAttribute( self, ns:Optional[str], name:str, value:Optional[str] ):
		if value is None:
			value_text = None
		elif self.RE_QUOTE.search(value):
			value_text = '"' + value.replace('"', '\\"') + '"'
		else:
			value_text = value
		# NOTE: We should have a formatting option here
		if self.attrIndex == 0 and not ns and name == "id" and value_text and value_text[0] != '"':
			yield f"#{value_text}"
		else:
			yield f" {ns+':' if ns else ''}{name}{'='+value_text if value else ''}"
		self.attrIndex += 1

	def onContentLine( self, text:str ):
		yield f"{self.indent}{text}\n"

	def onRawContentLine( self, text:str ):
		yield f"{self.indent}{text}\n"

	def onCommentLine( self, text:str, indent:int ):
		yield f"{'	' * indent}#{text}\n"

# -----------------------------------------------------------------------------
#
# XML DRIVER
#
# -----------------------------------------------------------------------------

class XMLEmitter(Emitter):
	"""A driver that emits an XML-serialized document (as a text string)."""

	def __init__( self ):
		super().__init__()
		self.isCurrentNodeClosed = True
		self.hasPreviousNode       = False
		self.isCurrentNodeEmpty    = True

	# =========================================================================
	# HANDLERS
	# =========================================================================

	def onDocumentStart( self, options:ParseOptions ):
		yield from super().onDocumentStart(options)
		yield '<?xml version="1.0"?>\n'

	def onDocumentEnd( self ):
		yield None

	def onNodeStart( self, ns:Optional[str], name:str, process:Optional[str] ):
		if not self.isCurrentNodeClosed:
			yield ">"
		yield f"<{ns+':' if ns else ''}{name}"
		self.hasPreviousNode = True
		self.isCurrentNodeEmpty = True
		self.isCurrentNodeClosed = False

	def onNodeContentStart( self, ns:Optional[str], name:str, process:Optional[str] ):
		yield None

	def onNodeEnd( self, ns:Optional[str], name:str, process:Optional[str] ):
		if self.isCurrentNodeEmpty:
			yield " />"
		else:
			yield f"</{ns+':' if ns else ''}{name}>"
		self.isCurrentNodeEmpty  = False
		self.isCurrentNodeClosed = True

	def onAttribute( self, ns:Optional[str], name:str, value:Optional[str] ):
		svalue = '"' + value.replace('"', '\\"') + '"' if value else ""
		attr   =  f" {ns}:{name}={svalue}" if ns else f" {name}={svalue}"
		yield attr

	def onContentLine( self, text:str ):
		if not self.isCurrentNodeClosed:
			yield ">"
			self.isCurrentNodeClosed = True
		else:
			yield "\n"
		self.isCurrentNodeEmpty = False
		yield self.escape(text)

	def onRawContentLine( self, text:str ):
		yield from self.onContentLine(text)

	def onCommentLine( self, text:str, indent:int ):
		if not self.isCurrentNodeClosed:
			yield ">"
			self.isCurrentNodeClosed = True
		self.isCurrentNodeEmpty = False
		if self.options.comments:
			yield (f"<!-- {text} -->\n")

	# =========================================================================
	# HELPERS
	# =========================================================================

	def escape( self, line ):
		return xml.sax.saxutils.escape(line)

# -----------------------------------------------------------------------------
#
# WRITER 
#
# -----------------------------------------------------------------------------

class Writer:
	"""A default writer that writes content to an output stream (stdout by
	default)."""

	def __init__( self, stream=sys.stdout ):
		self.out = stream

	def write( self, iterable ):
		"""Writes the iterable elements to the output stream."""
		for _ in iterable:
			if _ is None:
				pass
			elif isinstance(_, str):
				self.out.write(_)
			elif isinstance(_, ParseError):
				logging.error(str(_))
			else:
				self.out.write(json.dumps(_))
				self.out.write("\n")

class NullWriter(Writer):
	"""Absorbs the output."""

	def _write( self, iterable ):
		for _ in iterable:
			pass

# -----------------------------------------------------------------------------
#
# READER
#
# -----------------------------------------------------------------------------

class EmbeddedReader:
	"""Extracts TDoc content from a text file, wrapping the primary
	content in TDoc preformatted nodes."""

	# TODO: Start, Line and end (from options)
	def __init__( self,  parser:Parser ):
		self.parser  = parser
		self.node    = "code|tdoc"
		self.shebang = "#!"

	def read( self, iterable ):
		in_content = False
		embed_line = self.parser.options.embedLine or None
		for i,line in enumerate(iterable):
			# NOTE: The options might be mutated by the parser, so we need
			# to extract the prefix each time.
			if i == 0 and line.startswith(self.shebang):
				pass
			elif embed_line and line.startswith(embed_line):
				in_content = False
				yield line[len(embed_line):]
			elif not in_content:
				prefix = self.parser._indentPrefix * (self.parser.depth)
				yield f"{prefix}{self.node}"
				yield f"{prefix}{line}"
				in_content = True
			else:
				prefix = self.parser._indentPrefix * (self.parser.depth)
				yield f"{prefix}{line}"

# -----------------------------------------------------------------------------
#
# HIGH-LEVEL API
#
# -----------------------------------------------------------------------------

def parseIterable( iterable, out=sys.stdout, options=ParseOptions(), driver=Emitter.GetDefault() ):
	parser = Parser(options)
	if options.isEmbedded:
		iterable = EmbeddedReader(parser).read(_ for _ in iterable)
	return Writer(out).write(parser.parse(iterable, driver))

def parseString( text:str, out=sys.stdout, options=ParseOptions(), driver=Emitter.GetDefault() ):
	with open(path) as f:
		return parseIterable( (_[:-1] for _ in text.split("\n")), out=out, options=options, driver=driver)

def parsePath( path:str, out=sys.stdout, options=ParseOptions(), driver=Emitter.GetDefault() ):
	with open(path) as f:
		return parseIterable( f.readlines(), out=out, options=options, driver=driver)

def parseStream( stream, out=sys.stdout, options=ParseOptions(), driver=Emitter.GetDefault() ):
	return parseIterable( stream.readlines(), out=out, options=options, driver=driver)

EMITTERS = {
	"xml"    : XMLEmitter,
	"events" : EventEmitter,
	"tdoc"   : TDocEmitter,
}

if __name__ == "__main__":
	path = sys.argv[1]
	text = open(path).read() if os.path.exists(path) else path

# EOF - vim: ts=4 sw=4 noet
