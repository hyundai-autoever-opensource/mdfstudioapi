# -*- coding: utf-8 -*-
import argparse
import sys
import traceback
from datetime import datetime
from io import StringIO


def excepthook(exc_type, exc_value, tracebackobj):
    """
    Global function to catch unhandled exceptions.

    Parameters
    ----------
    exc_type : str
        exception type
    exc_value : int
        exception value
    tracebackobj : traceback
        traceback object
    """
    separator = "-" * 80

    now = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")

    info = StringIO()
    traceback.print_tb(tracebackobj, None, info)
    info.seek(0)
    info = info.read()

    errmsg = exc_type.__name__
    info = f"{exc_value}\t \n{info}"
    # errmsg = f"{exc_type}\t \n{exc_value}"
    sections = [now, errmsg, info]
    msg = "\t".join(sections)
    msg += "\n"

    print("".join(traceback.format_tb(tracebackobj)))
    print("{0}: {1}".format(exc_type, exc_value))

    Main.write_log(Main, message=msg)


def cmd_line_parser():

    parser = argparse.ArgumentParser()

    parser.add_argument("function", type=str)
    parser.add_argument("source", nargs='+', type=str)
    parser.add_argument("--subdir", action="store_true", default=False)

    parser.add_argument("--output-dir", dest="out_dir", type=str)
    parser.add_argument("--include-attr", dest="include_attr", action="store_true", default=False)

    parser.add_argument("--chn-dir", dest="chn_dir", type=str)
    parser.add_argument("--format", dest="format", type=str, default="csv")
    parser.add_argument("--include-stats", dest="stats", action="store_true", default=False)
    parser.add_argument("--resample", dest="raster", type=float)
    parser.add_argument("--groupby", dest="groupby", type=str, default="c")
    parser.add_argument("--with-index", dest="with_index", action="store_true", default=False)
    parser.add_argument("--start-time", dest="start_time", type=float)
    parser.add_argument("--end-time", dest="end_time", type=float)
    parser.add_argument("--from-zero", dest="from_zero", action="store_true", default=False)
    parser.add_argument("--empty-chn", dest="empty_chn", type=str, default="skip")
    parser.add_argument("--use-sname", dest="use_sname", action="store_true", default=False)

    return parser

def main():
    try:
        parser = cmd_line_parser()
    except:
        separator = "-" * 80
        now = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")

        message = "ApiException_009"
        details = f"Invalid parameter(s) entered.\t"
        # errmsg = f"{exc_type}\t \n{exc_value}"
        sections = [now, message, details]
        msg = "\t".join(sections)
        msg += "\n" + separator

        Main.write_log(Main, message=msg)
        return
    args = parser.parse_args()
    main = Main(args)

sys.excepthook = excepthook

if __name__ == "__main__":
    if __package__ is None:
        import sys
        from os import path

        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
        from API.main import Main
    else:
        from .main import Main
    main()