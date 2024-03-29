#!/usr/bin/env python3
from typing import (
    Optional,
    Any,
    Union,
    Iterable,
    Iterator,
    Generic,
    TypeVar,
    Type,
    Annotated,
    NamedTuple,
    cast,
)
import re, sys, os, logging, json, xml.sax.saxutils  # nosec B406
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass

T = TypeVar("T")

# try:
#     import tlang.tree as tlang_tree
# except ImportError as e:
#     tlang_tree = None

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


@dataclass
class ParseOption(Generic[T]):
    type: Type[T]
    default: Optional[T]
    help: str


class IndentMode(Enum):
    TABS = "TABS"
    SPACES = "SPACES"


class Doc(NamedTuple):
    value: str


@dataclass
class ParseOptions:
    comments: Annotated[bool, Doc("Includes comments in the output")] = False
    rootNode: Annotated[Optional[str], Doc("Tag name for the root node")] = None
    embed: Annotated[bool, Doc("Turns on embedded mode")] = False
    indentPrefix: Annotated[str, Doc("Indentation prefix")] = ""
    embedNode: Annotated[
        str, Doc("Tag name for embedded data in embedded mode")
    ] = "embed"
    embedLine: Annotated[
        Optional[str], Doc("Line prefix for embedded TDoc data (eg. '#')")
    ] = None
    embedStart: Annotated[
        Optional[str], Doc("Start of embedded TDoc data (eg. '/*')")
    ] = None
    embedEnd: Annotated[
        Optional[str], Doc("End of embedded TDoc data (eg. '*/')")
    ] = None

    @property
    def isEmbedded(self):
        return self.embed or self.embedLine or self.embedStart or self.embedEnd


@dataclass
class ParseError:
    """Define a parse error, that can be relayed by the writer."""

    line: int
    char: int
    message: str
    length: int = 0

    def __str__(self):
        return f"Syntax error at {self.line}:{self.char}: {self.message}"


ParseResult = Union[None, ParseError, str]


class ParsedAttribute(NamedTuple):
    ns: Optional[str]
    name: str
    value: str


class ParsedNode(NamedTuple):
    ns: Optional[str]
    name: str
    value: str
    attributes: list[ParsedAttribute]
    content: str


class StackItem(NamedTuple):
    depth: int
    ns: str
    name: str


NAME = r"[A-Za-z0-9\-_]+"
STR_SQ = r"'(\\'|[^'])*'"
STR_DQ = r'"(\\"|[^"])*"'

# A value is either a quoted string or a sequence without spaces
VALUE = f"({STR_SQ}|{STR_DQ}|" r"[^ \t\r\n]+)"
INLINE_ATTR = f"({NAME}:)?{NAME}={VALUE}"

# Attributes are like NAME=VALUE
# FIXME: Not sure where this is used, might be a @attr name=value
RE_ATTR = re.compile(f"[ \t]*((?P<ns>{NAME}):)?(?P<name>{NAME})=(?P<value>{VALUE})?")
RE_COMMENT = re.compile(r"^\t*#.*")

# Nodes are like NS:NAME|PARSER ATTR=VALUE: CONTENT
RE_NODE = re.compile(
    f"^((?P<ns>{NAME}):)?(?P<name>{NAME})"
    r"(#"
    f"(?P<id>{NAME})"
    r")?(\|"
    f"(?P<parser>{NAME}))?"
    f"(?P<attrs>([ ]+{INLINE_ATTR})*)?(: (?P<content>.*))?$"
)

# TODO: The parser should have a stack
class Parser:
    """The TDoc parser is implemented as a straightforward line-by-line
    parser with an event-based (SAX-like) interface.

    The parser uses iterators consistently as an abstraction over multiple
    sources and makes it possible to pause/resume parsing.
    """

    def __init__(self, options: ParseOptions = ParseOptions()):
        # TODO: These should be moved into the stack
        self.customParser: Optional[str] = None
        self.customParserDepth: Optional[int] = None
        self.options = options
        self.setIndent(IndentMode.TABS, 1)
        self.stack: list[StackItem] = []

    def setIndent(self, mode: IndentMode, count: int = 1):
        """Sets the indentation level for the parser. This updates the
        indentation prefix that is used to extract indentation from the parsed
        lines."""
        self._indentMode = mode
        self._indentCount = count
        self._indentPrefix = ("\t" if mode == IndentMode.TABS else " ") * count
        # The lastLineDepth is used to keep track of the depth of the last parsed
        # line, which is used by the embedded parser.
        self.lastLineDepth: int = 0
        self.options.indentPrefix = self._indentPrefix

    @property
    def depth(self):
        return self.stack[-1].depth if self.stack else 0

    def parse(self, iterable: Iterable[str], emitter: "Emitter"):
        """Parses the given iterable strings, using the given emitter to produce
        a result.

        This is equivalent to a combination of `start()`, `feed()` and `end()`,
        and is the preferred method to interact with a parser."""
        yield from self.start(emitter)
        for line in iterable:
            yield from self.feed(line, emitter)
        yield from self.end(emitter)

    def start(self, emitter: "Emitter[T]") -> Iterator[T]:
        """The parser is stateful, and `start` initializes its state."""
        self.customParser = None
        self.customParserDepth = None
        self.stack = []
        emitter.setOptions(self.options)
        yield from emitter.onDocumentStart(self.options)
        if self.options.rootNode:
            yield from emitter.onNodeStart(None, self.options.rootNode, None)
            yield from emitter.onNodeContentStart(None, self.options.rootNode, None)

    def end(self, emitter: "Emitter[T]") -> Iterator[T]:
        """Denotes the end of the parsing."""
        while self.stack:
            d = self.stack.pop()
            yield from emitter.onNodeEnd(d.ns, d.name, None)
        if self.options.rootNode:
            yield from emitter.onNodeEnd(None, self.options.rootNode, None)
        yield from emitter.onDocumentEnd()

    def feed(self, line: str, emitter: "Emitter[T]") -> Iterator[T]:
        """Feeds a line into the parser, which produces a directive for
        the emitter and may affect the state of the parser."""
        # We get the line indentation, store it as `i`
        depth, l = self.getLineIndentation(line)
        # NOTE: We use stopped as a way to exit the loop early, as we're
        # using an iterator.
        stopped = False
        self.lastLineDepth = depth
        # --- CUSTOM PARSER ---
        if self.customParser:
            # If we have CUSTOM PARSER, then we're going to feed RAW LINES
            if depth > (self.customParserDepth or 0):
                # BRANCH: RAW_CONTENT
                # That's a nested line, with an indentation greater than
                # the indentation of the custom parser
                yield from emitter.onRawContentLine(
                    self.stripLineIndentation(
                        line[:-1], (self.customParserDepth or 0) + 1
                    )
                )
                stopped = True
            elif not l:
                # BRANCH: RAW_CONTENT_EMPTY
                # This is an empty line, so we log it as an EOL
                yield from emitter.onRawContentLine("")
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
            yield from emitter.onCommentLine(l[1:-1], depth)
        elif self.isAttribute(l):
            # BRANCH: ATTRIBUTE
            # It's an ATTRIBUTE
            ns, name, value = self.parseAttributeLine(l[:-1])
            yield from self.onAttribute(emitter, ns, name, value)
        elif match := self.matchNode(l):
            # If is a node only if it's not too indented. If it is too
            # indented, it's a text.
            if depth > self.depth + 1:
                # BRANCH: TEXT CONTENT
                # The current line is TOO INDENTED (more than expected), so we consider
                # it to be TEXT CONTENT
                yield from emitter.onContentLine(l[:-1])
            else:
                # BRANCH: TEXT NODE
                # Here we're sure it's a NODE
                if depth <= self.depth:
                    # If it's DEDENTED, we need to pop the stack up until we
                    # reach a depth that's lower than `depth`.
                    while self.stack and self.depth >= depth:
                        d = self.stack.pop()
                        # STEP: END PREVIOUS NODE
                        yield from emitter.onNodeEnd(d.ns, d.name, None)
                else:
                    # Here, the indentation must be stricly one more level
                    # up.
                    if depth != self.depth + 1:
                        raise RuntimeError(
                            f"Parsing depth should be {self.depth + 1}, got {depth}"
                        )
                # We parse the node line
                ns, name, parser, attr, content = self.parseNode(match)
                self.stack.append(StackItem(depth, ns, name))
                if parser:
                    self.customParser = match["parser"]
                    self.customParserDepth = depth
                # Now we have the node start
                yield from emitter.onNodeStart(ns, name, parser)
                # Followed by the attributes, if any
                attr = list(attr)
                for ns, name, value in attr:
                    yield from self.onAttribute(emitter, ns, name, value)
                yield from emitter.onNodeContentStart(ns, name, parser)
                # And then the first line of content, if any
                if content is not None:
                    yield from emitter.onContentLine(content)
        elif self.isExplicitContent(l):
            yield from emitter.onContentLine(l[1:-1])
        else:
            # FIXME: See feature-whitespace, there's a problem there
            text = self.stripLineIndentation(line, self.depth)[:-1]
            if text:
                yield from emitter.onContentLine(text)

    # =========================================================================
    # PREDICATES
    # =========================================================================

    def isComment(self, line: str) -> bool:
        "Tells if the given line is a COMMENT line." ""
        return bool(RE_COMMENT.match(line))

    def isExplicitContent(self, line: str) -> bool:
        "Tells if the given line is an EXPLICIT CONTENT line." ""
        return bool(line and line[0] == ":")

    def matchNode(self, line: str) -> Optional[re.Match[str]]:
        """Tells if this line is node line"""
        return RE_NODE.match(line)

    def isAttribute(self, line: str) -> bool:
        """Tells if this line is attribute line"""
        return bool(line and line[0] == "@")

    # =========================================================================
    # HANDLERS
    # =========================================================================

    def onAttribute(
        self, emitter: "Emitter[T]", ns: Optional[str], name: str, value: Any
    ) -> Iterator[T]:
        if ns == "tdoc" and name == "indent":
            v = dict((k, v) for ns, k, v in self.parseAttributes(" " + value))
            if "spaces" in v:
                self.setIndent(IndentMode.SPACES, int(v.get("spaces", 4)))
            elif "tabs" in v:
                self.setIndent(IndentMode.TABS, int(v.get("tabs", 1)))
            else:
                raise SyntaxError(
                    f"tdoc:indent expects `tabs` or `spaces=N` as value, got: `{value}`"
                )
        else:
            yield from emitter.onAttribute(ns, name, value)

    # =========================================================================
    # SPECIFIC PARSERS
    # =========================================================================

    def parseNode(
        self, match: re.Match[str]
    ) -> tuple[str, str, str, list[tuple[Optional[str], str, str]], str]:
        attrs: list[ParsedAttribute] = [
            _ for _ in self.parseAttributes(match.group("attrs"))
        ]
        nid = match.group("id")
        if nid:
            l: list[ParsedAttribute] = ParsedAttribute(None, "id", nid)
            for _ in list(attrs):
                if _[1] == "id" and _[0] is None:
                    # TODO: We might want to issue a warning there
                    l[0] = _
                else:
                    l.append(_)
            attrs = l
        return ParsedNode(
            cast(str, match.group("ns")),
            cast(str, match.group("name")),
            cast(str, match.group("parser")),
            attrs,
            cast(str, match.group("content")),
        )

    def parseAttributes(self, line: str) -> Iterator[ParsedAttribute]:
        """Parses the attributes and returns a stream of `(key,value)` pairs."""
        # We remove the trailing spaces.
        while line and line[-1] in "\n \t":
            line = line[:-1]
        # Inline attributes are like
        #   ATTR=VALUE ATTR=VALUE…
        # Where value can be unquoted, single quoted or double quoted,
        # with \" or \' to escape quotes.
        o = 0
        while m := RE_ATTR.match(line, o):
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
            yield ParsedAttribute(m.group("ns"), m.group("name"), w or "")
            o = m.end()

    def parseAttributeLine(self, line):
        # Attributes are like
        #   @NAME VALUE
        # or
        #   @NS:NAME VALUE
        name_value = line.split(" ", 1)
        name = name_value[0][1:]
        ns_name = name.split(":", 1)
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

    def getLineIndentation(self, line: str) -> tuple[int, str]:
        """Returns the indentation for the line and the non-indented part of
        the line."""
        # TODO: We should support other indentation methods
        n = len(line)
        i = 0  # The indent level
        o = 0  # The character offset
        while o < n and line.startswith(self._indentPrefix, o):
            i += 1
            o += len(self._indentPrefix)
        l = line[o:] if o > 0 else line
        return i, l

    def stripLineIndentation(self, line: str, indent: int) -> str:
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


class Emitter(ABC, Generic[T]):
    """An abstract interface for the parser emitter. The emitter yields
    values that are then handled by a writer. In other words, it transforms
    the stream of events produced by the parser in a stream of values to
    be written."""

    @classmethod
    def GetDefault(cls):
        return XMLEmitter()

    def __init__(self):
        self.options: Optional[ParseOptions] = None

    def setOptions(self, options: Optional[ParseOptions]):
        self.options = options
        return self

    @abstractmethod
    def onDocumentStart(self, options: ParseOptions) -> Iterator[T]:
        ...

    @abstractmethod
    def onDocumentEnd(self) -> Iterator[T]:
        ...

    @abstractmethod
    def onNodeStart(
        self, ns: Optional[str], name: str, process: Optional[str]
    ) -> Iterator[T]:
        ...

    @abstractmethod
    def onNodeContentStart(
        self, ns: Optional[str], name: str, process: Optional[str]
    ) -> Iterator[T]:
        ...

    @abstractmethod
    def onNodeEnd(
        self, ns: Optional[str], name: str, process: Optional[str]
    ) -> Iterator[T]:
        ...

    @abstractmethod
    def onAttribute(
        self, ns: Optional[str], name: str, value: Optional[str]
    ) -> Iterator[T]:
        ...

    @abstractmethod
    def onContentLine(self, text: str) -> Iterator[T]:
        ...

    @abstractmethod
    def onRawContentLine(self, text: str) -> Iterator[T]:
        ...

    @abstractmethod
    def onCommentLine(self, text: str, indent: int) -> Iterator[T]:
        ...


# -----------------------------------------------------------------------------
#
# EVENT DRIVER
#
# -----------------------------------------------------------------------------


class EventEmitter(Emitter):
    """A emitter that outputs an event stream."""

    def __init__(self):
        self.options = None

    def onDocumentStart(self, options: ParseOptions):
        self.options = options
        yield ("DocumentStart",)

    def onDocumentEnd(self):
        yield ("DocumentEnd",)

    def onNodeStart(self, ns: Optional[str], name: str, process: Optional[str]):
        yield ("NodeStart", ns, name, process)

    def onNodeEnd(self, ns: Optional[str], name: str, process: Optional[str]):
        yield ("NodeEnd", ns, name, process)

    def onAttribute(self, ns: Optional[str], name: str, value: Optional[str]):
        yield ("Attribute", ns, name, value)

    def onContentLine(self, text: str):
        yield ("Content", text)

    def onRawContentLine(self, text: str):
        yield ("RawContent", text)

    def onCommentLine(self, text: str, indent: int):
        yield ("Comment", text)


# -----------------------------------------------------------------------------
#
# NULL EMITTER
#
# -----------------------------------------------------------------------------


class NullEmitter(Emitter):
    """A emitter that outputs nothing."""

    def onDocumentStart(self, options: ParseOptions):
        yield None

    def onDocumentEnd(self):
        yield None

    def onNodeStart(self, ns: Optional[str], name: str, process: Optional[str]):
        yield None

    def onNodeEnd(self, ns: Optional[str], name: str, process: Optional[str]):
        yield None

    def onAttribute(self, ns: Optional[str], name: str, value: Optional[str]):
        yield None

    def onContentLine(self, text: str):
        yield None

    def onRawContentLine(self, text: str):
        yield None

    def onCommentLine(self, text: str, indent: int):
        yield None


# -----------------------------------------------------------------------------
#
# TDOC DRIVER
#
# -----------------------------------------------------------------------------


class TDocEmitter(Emitter[Optional[str]]):
    """A emitter that outputs a normalized TDoc document."""

    RE_QUOTE = re.compile('[" ]')

    def __init__(self):
        self.options = None
        self.indent = ""
        self.attrIndex = 0

    def onDocumentStart(self, options: ParseOptions):
        self.options = options
        yield None

    def onDocumentEnd(self):
        yield None

    def onNodeStart(self, ns: Optional[str], name: str, process: Optional[str]):
        yield f"{self.indent}{ns+':' if ns else ''}{name}{'|'+process if process else ''}"
        self.indent += "\t"
        self.attrIndex = 0

    def onNodeContentStart(self, ns: Optional[str], name: str, process: Optional[str]):
        yield "\n"

    def onNodeEnd(self, ns: Optional[str], name: str, process: Optional[str]):
        self.indent = self.indent[:-1]
        yield None

    def onAttribute(self, ns: Optional[str], name: str, value: Optional[str]):
        if value is None:
            value_text = None
        elif self.RE_QUOTE.search(value):
            value_text = '"' + value.replace('"', '\\"') + '"'
        else:
            value_text = value
        # NOTE: We should have a formatting option here
        if (
            self.attrIndex == 0
            and not ns
            and name == "id"
            and value_text
            and value_text[0] != '"'
        ):
            yield f"#{value_text}"
        else:
            yield f" {ns+':' if ns else ''}{name}{'='+value_text if value_text else ''}"
        self.attrIndex += 1

    def onContentLine(self, text: str):
        yield f"{self.indent}{text}\n"

    def onRawContentLine(self, text: str):
        yield f"{self.indent}{text}\n"

    def onCommentLine(self, text: str, indent: int):
        yield f"{'	' * indent}#{text}\n"


# -----------------------------------------------------------------------------
#
# XML DRIVER
#
# -----------------------------------------------------------------------------


class XMLEmitter(Emitter):
    """A emitter that emits an XML-serialized document (as a text string)."""

    def __init__(self):
        super().__init__()
        self.isCurrentNodeClosed = True
        self.hasPreviousNode = False
        self.isCurrentNodeEmpty = True

    # =========================================================================
    # HANDLERS
    # =========================================================================

    def onDocumentStart(self, options: ParseOptions):
        yield '<?xml version="1.0"?>\n'

    def onDocumentEnd(self):
        yield None

    def onNodeStart(self, ns: Optional[str], name: str, process: Optional[str]):
        if not self.isCurrentNodeClosed:
            yield ">"
        if ns == "pi":
            yield f"<?{name}"
        else:
            yield f"<{ns+':' if ns else ''}{name}"
        self.hasPreviousNode = True
        self.isCurrentNodeEmpty = True
        self.isCurrentNodeClosed = False

    def onNodeContentStart(self, ns: Optional[str], name: str, process: Optional[str]):
        yield None

    def onNodeEnd(self, ns: Optional[str], name: str, process: Optional[str]):
        if ns == "pi":
            yield "?>\n"
        elif self.isCurrentNodeEmpty:
            yield " />"
        else:
            yield f"</{ns+':' if ns else ''}{name}>"
        self.isCurrentNodeEmpty = False
        self.isCurrentNodeClosed = True

    def onAttribute(self, ns: Optional[str], name: str, value: Optional[str]):
        svalue = '"' + value.replace('"', '\\"') + '"' if value else ""
        attr = f" {ns}:{name}={svalue}" if ns else f" {name}={svalue}"
        yield attr

    def onContentLine(self, text: str):
        if not self.isCurrentNodeClosed:
            yield ">"
            self.isCurrentNodeClosed = True
        else:
            yield "\n"
        self.isCurrentNodeEmpty = False
        yield self.escape(text)

    def onRawContentLine(self, text: str):
        yield from self.onContentLine(text)

    def onCommentLine(self, text: str, indent: int):
        if not self.isCurrentNodeClosed:
            yield ">"
            self.isCurrentNodeClosed = True
        self.isCurrentNodeEmpty = False
        if self.options and self.options.comments:
            yield (f"<!-- {text} -->\n")

    # =========================================================================
    # HELPERS
    # =========================================================================

    def escape(self, line: str) -> str:
        # NOTE: This could be rewritten
        return xml.sax.saxutils.escape(line)


# -----------------------------------------------------------------------------
#
# TLANG EMITTER
#
# -----------------------------------------------------------------------------


# class TLangEmitter(Emitter):
#     """A emitter that outputs nothing."""
#
#     def onDocumentStart(self, options: ParseOptions):
#         self.root = tlang_tree.Node(options.rootNode or "document")
#         self.node = self.root
#         yield None
#
#     def onDocumentEnd(self):
#         yield self.root
#
#     def onNodeStart(self, ns: Optional[str], name: str, process: Optional[str]):
#         name = ns + ":" + name if ns else name
#         node = tlang_tree.Node(name)
#         self.node.append(node)
#         self.node = node
#         yield None
#
#     def onNodeEnd(self, ns: Optional[str], name: str, process: Optional[str]):
#         self.node = self.node.parent
#         yield None
#
#     def onAttribute(self, ns: Optional[str], name: str, value: Optional[str]):
#         name = ns + ":" + name if ns else name
#         if self.node:
#             self.node.attr(name, value)
#         else:
#             # TODO: Should warn about that
#             pass
#         yield None
#
#     def onContentLine(self, text: str):
#         self.node.append(tlang_tree.Node("#text").attr("value", text))
#         yield None
#
#     def onRawContentLine(self, text: str):
#         self.node.append(tlang_tree.Node("#text").attr("value", text).attr("raw", True))
#         yield None
#
#     def onCommentLine(self, text: str, indent: int):
#         self.node.append(
#             tlang_tree.Node("#comment").attr("value", text).attr("indent", indent)
#         )
#         yield None


# -----------------------------------------------------------------------------
#
# WRITER
#
# -----------------------------------------------------------------------------


class Writer:
    """A default writer that writes content to an output stream (stdout by
    default)."""

    def __init__(self, stream=sys.stdout):
        self.out = stream

    def write(self, iterable):
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

    def __call__(self, out):
        self.out = out
        return self


class NullWriter(Writer):
    """Absorbs the output."""

    def _write(self, iterable):
        for _ in iterable:
            pass


class ValueWriter(Writer):
    """Returns the last value yielded by the emitter."""

    def write(self, iterable):
        result = None
        for _ in iterable:
            if _ is not None:
                result = _
        return result


# -----------------------------------------------------------------------------
#
# READER
#
# -----------------------------------------------------------------------------


class EmbeddedReader:
    """Extracts TDoc content from a text file, wrapping the primary
    content in TDoc preformatted nodes."""

    # TODO: Start, Line and end (from options)
    def __init__(self, parser: Parser):
        self.parser = parser
        self.shebang = "#!"

    def read(self, iterable):
        in_content = False
        embed_line = self.parser.options.embedLine or None
        embed_node = self.parser.options.embedNode or "embed|raw"
        for i, line in enumerate(iterable):
            # NOTE: The options might be mutated by the parser, so we need
            # to extract the prefix each time.
            if i == 0 and line.startswith(self.shebang):
                pass
            elif embed_line and line.startswith(embed_line):
                in_content = False
                yield line[len(embed_line) :]
            elif not in_content:
                prefix = self.parser._indentPrefix * (self.parser.lastLineDepth)
                if embed_node:
                    yield f"{prefix}{embed_node}"
                yield f"{prefix}{line}"
                in_content = True
            else:
                prefix = self.parser._indentPrefix * (self.parser.lastLineDepth)
                yield f"{prefix}{line}"


# -----------------------------------------------------------------------------
#
# HIGH-LEVEL API
#
# -----------------------------------------------------------------------------


def parseIterable(
    iterable,
    out=sys.stdout,
    options=ParseOptions(),
    emitter=Emitter.GetDefault(),
    writer=Writer(),
):
    parser = Parser(options)
    if options.isEmbedded:
        iterable = EmbeddedReader(parser).read(_ for _ in iterable)
    return writer(out).write(parser.parse(iterable, emitter))


def parseString(
    text: str,
    out=sys.stdout,
    options=ParseOptions(),
    emitter=Emitter.GetDefault(),
    writer=Writer(),
):
    return parseIterable(
        (_[:-1] for _ in text.split("\n")),
        out=out,
        options=options,
        emitter=emitter,
        writer=writer,
    )


def parsePath(
    path: str,
    out=sys.stdout,
    options=ParseOptions(),
    emitter: Emitter = Emitter.GetDefault(),
    writer=Writer(),
):
    with open(path) as f:
        return parseIterable(
            f.readlines(), out=out, options=options, emitter=emitter, writer=writer
        )


def parseStream(
    stream,
    out=sys.stdout,
    options=ParseOptions(),
    emitter: Emitter = Emitter.GetDefault(),
    writer=Writer(),
):
    return parseIterable(
        stream.readlines(), out=out, options=options, emitter=emitter, writer=writer
    )


EMITTERS: dict[str, Type[Emitter]] = {
    "xml": XMLEmitter,
    "events": EventEmitter,
    "tdoc": TDocEmitter,
    "null": NullEmitter,
}

if __name__ == "__main__":
    path = sys.argv[1]
    text = open(path).read() if os.path.exists(path) else path

# EOF - vim: ts=4 sw=4 et
