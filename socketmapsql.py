#!/usr/bin/env python3
"""
An implementation of the sendmail socketmap protocol to allow an SQL database
to be queried out of process.
"""

import argparse
import contextlib
import configparser
import importlib
import os.path
import re
import select
import subprocess
import sys


__version__ = "0.1.0"


FUNC_REF_PATTERN = re.compile(
    r"""
    ^
    (?P<module>
        [a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*
    )
    :
    (?P<object>
        [a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*
    )
    $
    """,
    re.I | re.X,
)


def match(name):
    matches = FUNC_REF_PATTERN.match(name)
    if not matches:
        raise ValueError("Malformed callable '{}'".format(name))
    return matches.group("module"), matches.group("object")


def resolve(module_name, obj_name):
    """
    Resolve a named object in a module.
    """
    return getattr(importlib.import_module(module_name), obj_name)


class MalformedNetstringError(Exception):
    pass


def read_netstring(fp):
    """
    Reads a single netstring.
    """
    n = ""
    while True:
        c = fp.read(1)
        if c == "":
            return None
        if c == ":":
            break
        if len(n) > 10:
            raise MalformedNetstringError
        if c == "0" and n == "":
            # We can't allow leading zeros.
            if fp.read(1) != ":":
                raise MalformedNetstringError
            n = c
            break
        n += c
    n = int(n, 10)
    result = ""
    while n > 0:
        segment = fp.read(n)
        n -= len(segment)
        result += segment
    if fp.read(1) != ",":
        raise MalformedNetstringError
    return result


def write_netstring(fp, response):
    fp.write("{}:{},".format(len(response), response))
    fp.flush()


def parse_config(fp):
    def process_local(local_part, cfg):
        delimiter = cfg.get("recipient_delimiter", "").strip()
        if delimiter != "":
            local_part = local_part.split(delimiter, 1)[0]
        return local_part

    def split(arg, cfg):
        parts = arg.split("@", 1)
        parts[0] = process_local(parts[0], cfg)
        parts[1] = parts[1].lower()
        return parts

    transforms = {
        "all": lambda arg, cfg: [arg],
        "lowercase": lambda arg, cfg: [arg.lower()],
        "local": lambda arg, cfg: [process_local(arg.split("@", 1)[0], cfg)],
        "domain": lambda arg, cfg: [arg.split("@", 1)[1].lower()],
        "split": split,
    }

    cp = configparser.RawConfigParser()
    cp.readfp(fp)

    result = {
        "database": dict(cp.items("database")),
        "tables": {},
        "misc": dict(cp.items("misc")),
    }

    for section in cp.sections():
        if section.startswith("table:"):
            _, table_name = section.split(":", 1)
            if not cp.has_option(section, "query"):
                continue

            try:
                transform_name = cp.get(section, "transform")
            except configparser.NoOptionError:
                transform_name = "all"
            transform = transforms.get(transform_name)
            if transform is None:
                transform = resolve(*match(transform_name))

            result["tables"][table_name] = {
                "transform": transform,
                "query": cp.get(section, "query"),
            }

    return result


def serve_client(fh_in, fh_out, conn, timeout, tables, cfg):
    try:
        while True:
            # Wait a short period before exiting.
            iready, _, _ = select.select([fh_in], (), (), timeout)
            if len(iready) == 0:
                break

            request = read_netstring(fh_in)

            table_name, arg = request.split(" ", 1)

            table = tables.get(table_name)
            if table is None:
                write_netstring(fh_out, "PERM no such table: " + table_name)
                continue

            cur = conn.cursor()
            try:
                cur.execute(table["query"], table["transform"](arg, cfg))
                result = cur.fetchone()
            finally:
                cur.close()

            if result is None:
                write_netstring(fh_out, "NOTFOUND ")
            else:
                write_netstring(fh_out, "OK " + str(result[0]))
    except MalformedNetstringError:
        write_netstring(fh_out, "PERM malformed netstring")
    except Exception as exc:
        write_netstring(fh_out, "PERM " + str(exc))


def connect(settings):
    """
    Connect to a database.
    """
    driver = importlib.import_module(settings.pop("driver", "sqlite3"))
    return driver.connect(**settings)


def main():
    parser = argparse.ArgumentParser(description="Database socketmap daemon.")
    parser.add_argument(
        "--config",
        help="Path to config file",
        type=argparse.FileType(),
        default="/etc/socketmap-sql.ini",
    )
    parser.add_argument(
        "--timeout",
        help="Number of seconds to wait before exiting",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--client", action="store_true", help="Start with a debug client"
    )
    args = parser.parse_args()

    with contextlib.closing(args.config):
        cfg = parse_config(args.config)

    if args.client:
        svr_args = [arg for arg in sys.argv if arg != "--client"]
        svr_args[0] = os.path.abspath(svr_args[0])
        proc = subprocess.Popen(
            svr_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8"
        )
        print("Type '.exit' to exit.")
        while proc.poll() is None:
            req = input("socketmap> ")
            if req == ".exit":
                proc.terminate()
                break
            write_netstring(proc.stdin, req)
            print(read_netstring(proc.stdout))
    else:
        with contextlib.closing(connect(cfg["database"])) as conn:
            serve_client(
                sys.stdin, sys.stdout, conn, args.timeout, cfg["tables"], cfg["misc"]
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

# vim:set ft=python et:
