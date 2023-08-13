import sys, argparse
from typing import Optional, Type, Any
from tdoc.parser import EMITTERS, Emitter, ParseOptions, parsePath
import os


def doc(t: Type, field: str) -> Optional[str]:
    if field in t.__annotations__:
        return f"{t.__annotations__[field]}"
    else:
        return None


def run(args: Optional[list[str]] = None, name="tdoc") -> int:
    """Command-line interface to the TDoc parser."""
    if args is None:
        args = sys.argv[1:]
    oparser = argparse.ArgumentParser(
        prog=name or os.path.basename(__file__.split(".")[0]),
        description="Parser and transpiler for TDoc <http://tlang.org/tdoc>",
    )
    oparser.add_argument(
        "files",
        metavar="FILE",
        type=str,
        nargs="*",
        help="The .tdoc source files to process",
    )
    oparser.add_argument(
        "-O",
        "--output-format",
        action="store",
        dest="outputFormat",
        choices=list(EMITTERS.keys()),
        default=next(_ for _ in EMITTERS),
        help=doc(ParseOptions, "outputFormat"),
    )
    oparser.add_argument(
        "-r",
        "--root",
        action="store",
        dest="rootNode",
        help=doc(ParseOptions, "rootNode"),
    )
    oparser.add_argument(
        "-c",
        "--with-comments",
        action="store_true",
        dest="comments",
        help=doc(ParseOptions, "comments"),
    )
    oparser.add_argument(
        "-e",
        "--embed",
        action="store_true",
        help="""TDoc is embedded in another language. Will try to autodetect
		language, if `--embed-{start,line,end}` are not specified.""",
    )
    oparser.add_argument(
        "-en",
        "--embed-node",
        type=str,
        default=None,
        dest="embedNode",
        help=doc(ParseOptions, "embedNode"),
    )
    oparser.add_argument(
        "-es",
        "--embed-start",
        type=str,
        default=None,
        dest="embedStart",
        help=doc(ParseOptions, "embedStart"),
    )
    oparser.add_argument(
        "-el",
        "--embed-line",
        type=str,
        default=None,
        dest="embedLine",
        help=doc(ParseOptions, "embedLine"),
    )
    oparser.add_argument(
        "-ee",
        "--embed-end",
        type=str,
        default=None,
        dest="embedEnd",
        help=doc(ParseOptions, "embedLEnd"),
    )
    # We create the parse and register the options
    opts = oparser.parse_args(args=args)
    # We extract parser optios
    parse_options = ParseOptions(
        **{k: v for k, v in vars(opts).items() if k not in ("files", "outputFormat")}
    )
    emitter: Emitter[Any] = EMITTERS[opts.outputFormat]()
    for path in opts.files:
        parsePath(path, options=parse_options, emitter=emitter)
    return 0


if __name__ == "__main__":
    res = run()
    sys.exit(res)

# EOF - vim: ts=4 sw=4 et
