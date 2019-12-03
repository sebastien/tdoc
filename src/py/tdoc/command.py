import sys, argparse
from typing import Optional, List
from tdoc.parser import EMITTERS, ParseOptions, parseString, parsePath

def run( args:Optional[List[str]]=None, name="tdoc" ):
	"""Command-line interface to the TDoc parser."""
	if args is None: args = sys.argv[1:]
	if type(args) not in (type([]), type(())): args = [args]
	oparser = argparse.ArgumentParser(
		prog        = name or os.path.basename(__file__.split(".")[0]),
		description = "Parser and transpiler for TDoc <http://tlang.org/tdoc>"
	)
	oparser.add_argument("files", metavar="FILE", type=str, nargs='*',
		help='The .tdoc source files to process')
	oparser.add_argument("-O", "--output-format", action="store", dest="outputFormat",
		choices=list(EMITTERS.keys()), default=next(_ for _ in EMITTERS),
		help=ParseOptions.OPTIONS["comments"].help)
	oparser.add_argument("-D", "--with-document", action="store", dest="document", default="document",
		help=ParseOptions.OPTIONS["document"].help)
	oparser.add_argument("-c", "--with-comments", action="store_true", dest="comments",
		help=ParseOptions.OPTIONS["comments"].help)
	oparser.add_argument("-e", "--embed", action="store_true",
		help="""TDoc is embedded in another language. Will try to autodetect
		language, if `--embed-{start,line,end}` are not specified.""")
	oparser.add_argument("-es", "--embed-start", type=str, default=None, dest="embedStart",
		help=ParseOptions.OPTIONS["embedStart"].help)
	oparser.add_argument("-el", "--embed-line", type=str, default=None, dest="embedLine",
		help=ParseOptions.OPTIONS["embedLine"].help)
	oparser.add_argument("-ee", "--embed-end", type=str, default=None,dest="embedEnd",
		help=ParseOptions.OPTIONS["embedEnd"].help)
	# We create the parse and register the options
	opts = oparser.parse_args(args=args)
	# We extract parser optios
	parse_options = ParseOptions(vars(opts))
	driver = EMITTERS[opts.outputFormat]()
	for path in opts.files:
		res  = parsePath(path, options=parse_options, driver=driver)

if __name__ == '__main__':
	res = run()

# EOF - vim: ts=4 sw=4 noet
