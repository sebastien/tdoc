#!/usr/bin/python
# Encoding: utf8

import sys, os
from distutils.core import setup

VERSION     = os.popen("""grep __version__ src/py/tdoc/__init__.py | head -n1 | cut -d'"' -f2""").read().split("\n")[0]
SUMMARY     = "Tree Document Format"
DESCRIPTION = """\
TDoc is a text format to write XML-compatible trees.
"""

# ------------------------------------------------------------------------------
#
# SETUP DECLARATION
#
# ------------------------------------------------------------------------------

setup(
	name        = "tlang-tdoc",
	version     = VERSION,
	author      = "Sebastien Pierre", author_email = "sebastien.pierre@gmail.com",
	description = SUMMARY, long_description = DESCRIPTION,
	license     = "Revised BSD License",
	keywords    = "xml tree document markup syntax parser".split(),
	url         = "https://hg.sr.ht/~sebastien/tdoc/",
	download_url= f"https://hg.sr.ht/~sebastien/tdoc/archive/{VERSION}.tar.gz" ,
	package_dir = { "": "src/py" },
	packages    = ["tdoc"],
	scripts     = ["bin/tdoc"],
	classifiers = [
	"Development Status :: 4 - Beta",
	"Environment :: Console",
	"Intended Audience :: Developers",
	"Intended Audience :: Information Technology",
	"License :: OSI Approved :: BSD License",
	"Natural Language :: English",
	"Topic :: Documentation",
	"Topic :: Software Development :: Documentation",
	"Topic :: Text Processing",
	"Topic :: Text Processing :: Markup",
	"Topic :: Text Processing :: Markup :: HTML",
	"Topic :: Text Processing :: Markup :: XML",
	"Topic :: Utilities",
	"Operating System :: POSIX",
	"Operating System :: Microsoft :: Windows",
	"Programming Language :: Python",
	]
)

# EOF - vim: tw=80 ts=4 sw=4 noet
