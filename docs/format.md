# Tree document format

The tree document format (or *tdoc* for short) is a way to easily write
tree-structured data using a regular text editor. This format makes it
possible to embed other languages within the document (markdown,
javascript, CSV, etc) and also embed TDoc within another language.

Embedded languages are either left unparsed, as raw strings, or parsed
as a tree structure, when a rich parser is available.

As such, it provides an easy way to wrap existing code in a tree
structure, and create hybrid documents that contain more than one
language.

The tree block syntax is a tab-indented format, where the nesting of
content is primarily determined by the indentation level. This is not a
hard rule, however, as the `tdoc` command also supports
space-indentation.

# Syntax

## Nodes

Nodes have a *name* (which can optionally be prefixed by a
*namespace*),and optional *attributes*.

The node is then followed by an optional first line of content,
separated by `: ` (note the space after the colon). The rest of the
content is then within one level of indentation relative to the node.

    NODE: TEXT
        CONTENT

Here is an example of an HTML document encoded in tdoc:

``` tdoc
html
    body
        h1: Hello, world
        p: Lorem ipsum dolor sit amet
```

In case where your content might be accidentaly intepreted as a node
declaration, you can prefix it directly with `:` (no extra space
needed), like so:

``` tdoc
p
    :hello
    :world
```

Note that there is no way to encode a node inline, ie. you can only have
one node per line. That means that the following HTML code:

``` html
<p>Hello, <em>World</em>!<p>
```

can only be written

``` tdoc
p: Hello,
    em: World
    !
```

## Attributes

Attributes in a node can be declared with the `ATTR=VALUE` syntax, like
so:

``` tdoc
body style=background-color:#E0E0E0;padding:40px; lang=en
```

In case the attribute value contains a space, you can quote the string
using double `"` or single `'` quotes, escaping inner quotes with a
backslash `\\` like in pretty much all languages.

``` tdoc
button title='Don\'t click me!'
```

In case you want to have an attribute with no value, suffix its name
with `=`

``` tdoc
button disabled=: Save
```

Alternatively, attributes can be defined as content using the
`@ATTR VALUE` notation:

``` tdoc
rect
    @width 300
    @height 200
```

When used this way, there can be only one attribute per line, and you
don't have to use quotes (but you can if you want to).

## Namespaces

XML and XSLT make extensive use of namespace to combine documents, and
namespaces should be available both in nodes and attributes. In TDoc,
namespaces prefix node or attribute names and are followed by `:`, with
no space so as not to clash with the `: ` content separator
(`NAMESPACE:NAME`):

``` tdoc
html xmlns:svg=http://www.w3.org/2000/svg
    body
        svg:svg width=200 height=200
            svg:circle
                @svg:cx 100
                @svg:cy 100
                @svg:r 100
```

## Node names

There is a shorthand syntax for the `node id=myNodeName"` in the form:

``` tdoc
NODE#NAME
```

## Parsers

Node content can be specified as being expressed in a different syntax,
for instance if you're embedding a block of markdown text, or some C or
Python code. In that case, you can suffix the node declaration with a
`|` followed by your parser's name:

``` tdoc
p|markdown
    Hello, *world*!
code|c
    #include <stdio.h>
    void main void {
        printf("Hello, world!\n");
    }
```

By using parsers, you delegate the parsing of the content (any
contiguous block with at least one more indentation level) to the parser
with the given name.

This means that any line that the set of contiguous line with an
indentation level greater than the node with the custom parser is going
to be fed as-is to the custom parser.

If the parser is registered within tdoc's interpreter, then the content
might be parsed and expanded to a tree, otherwise it's going to be
integrated as a raw string, after the initial indentation is removed.

Note that parsers should be defined just after the node name, so you can
still write attributes after

``` tdoc
pre|javascript id=myscript
    function(){
        …
    }
```

## Comments

Comments are lines that start with a hash `#`, and might be indented at
any level. If you have a node content that starts with a hash, you can
use the same content escaping trick as if you content could be
interpreted as node:

``` tdoc
p
    :# This is not a comment.
```

However, when the `#` is contained within a node that has a custom
parser, then the line will be considered content if it has an
indentation greater than the indentation of the node with the custom
parser.

## White space

It's good to note that whitespace is entirely preserved by tdoc, once
the indentation, separators and end of line have been removed. This
means that the following TDoc document:

``` tdoc
p
    lorem ipsum
    dolor sit amet
```

would, converted to a Lisp-like structure yield:

``` scheme
(p "lorem ipsum" "dolor sit amet")
```

Meaning that you'll need to join the two lines with a space or newline
if you want to have `lorem ipsum dolor sit amet` instead of
`lorem ipsumdolor sit amet`.

There are some specific cases to think about, though, especially when it
comes to empty lines:

    --INDENT--
    If a line has only tabs and spaces, it is not empty: the spaces count as
    content (which is what is expected, because TDoc preserves whitespace)

``` tdoc
p
    This is not an empty line
    # The line below is empty ie. (\t\n) ― it contains only indentation

    # The line below is NOT empty (\t \n) ― it contains a space right after the indent
```

If a line has only indentation, but has an indentation greater than a
parent block then it is not an empty line, and any character after the
parent's indent level + 1 is taken as content:

``` tdoc
code
    def foo():
        print("spam")
```

will yield

``` scheme
(p "def foo():" "\tprint(\"spam\")")
```

If a line has only indentation, which is lower or equal to the current
parent's, then it is taken as an empty line and skipped, unless it is
within a block with a custom parser.

Empty lines are usually ignored except in the case where a parser is
used (like in `section|markdown`), in which case an empty line is
interpreted as an `\n` in the reconstructed code.

``` tdoc
code|js
    function hello(){
        console.log("Hello,world")
    }

    hello();
```

will result in

``` scheme
(code "function hello(){\n\tconsole.log(\"Hello,world\")\n}\nhello();\n")
```

Another special treatment is that in that case the indentation of the
line is irrelevant if lesser or equal than the current block
indentation.

# Embedded mode

TDoc can also be used as embedded in another language. For instance, if
you're writing a program and would like to add structured data, add
embedded documentation or write your code in a litterate programming
approach:

```` c
/**
title: An example of embedded TDoc
p|markdown
    You'd invoke this using
    ```shell
    tdoc -Iembed --embed-start='/**' --embed=end='*/'
    ```
*/
#include <stdio.h>
void main(void){
    print("Hello, world!\n");
}
````

processing with `tdoc -e` would yield the following tree:

``` tdoc
```

or if you're using single-line comments,

``` bash
## title: An example of embedded TDoc
## p|markdown
##  You'd invoke this using
##  ```shell
##  tdoc -Iembed='## '
echo "Hello, world"
```

## Specifying indentation

You can specify directives by using nodes and attributes in the `tdoc`
namespace. For instance, you can have a top-level attribute defining how
the parsing should happen:

``` tdoc
@tdoc:indent spaces=2
```

``` tdoc
@tdoc:indent tabs
```

will tell TDoc to consider two spaces as the default indentation. You
could do `@tdoc:indent tabs` or `@tdoc:indent spaces=4`, etc.

## Specifying content nesting

Code will be wrapped in `code` nodes and inserted as a child of the
current parent. In the following example, we want to make sure the
function's code is not nested under the `param` node:

``` python
## section#functions title="Function definition"
##   function#hello_world
##     param name=message type=str default="Hello, world"
##        The message to be displayed
##     :
def hello_world(message='Hello, world!'):
    """Prints 'Hello, world!'."""
    print (message)
```

To do so, we add an empty line, denoted by `:`, that will set the
`function` node as the current parent.

# Related work

- HAML, PAML, Pug: these languages are all meant to writing (HT\|X)ML
  more easily. TDoc's design is actually derived from years of writing
  XML and XSLT using PAML, and tries to keep the good parts while
  simplyfing the syntax further.

- TreeNotation: while conceptually closer, tree notation is hard to
  understand because it lacks a clear definition.
