#!/usr/bin/env python3
"""
An implementation of the sendmail socketmap protocol to allow an SQL database
to be queried out of process.
"""

import argparse
import configparser
import contextlib
import dataclasses
import importlib
import io
import os.path
import re
import select
import subprocess
import sys
from typing import Callable, Dict, List, Mapping, Optional, Tuple, TypedDict


__version__ = "0.2.0"


Transform = Callable[[str, Mapping[str, str]], List[str]]


@dataclasses.dataclass
class TableCfg:
    query: str
    transform: Transform


class Cfg(TypedDict):
    database: Dict[str, str]
    misc: Dict[str, str]
    tables: Dict[str, TableCfg]


FUNC_REF_PATTERN = re.compile(
    r"""
    ^
    (?P<module>[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)
    :
    (?P<object>[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)
    $
    """,
    re.I | re.X,
)


def match(name: str) -> Tuple[str, str]:
    matches = FUNC_REF_PATTERN.match(name)
    if not matches:
        raise ValueError(f"Malformed callable '{name}'")
    return matches.group("module"), matches.group("object")


def resolve(module_name: str, obj_name: str) -> Callable:
    """
    Resolve a named object in a module.
    """
    return getattr(importlib.import_module(module_name), obj_name)


class MalformedNetstringError(Exception):
    pass


def read_netstring(fp: io.TextIOWrapper) -> Optional[str]:
    """
    Reads a single netstring.
    """
    ns = ""
    while True:
        c = fp.read(1)
        if c == "":
            return None
        if c == ":":
            break
        if len(ns) > 10:
            raise MalformedNetstringError
        if c == "0" and ns == "":
            # We can't allow leading zeros.
            if fp.read(1) != ":":
                raise MalformedNetstringError
            ns = c
            break
        ns += c
    n = int(ns, 10)
    result = ""
    while n > 0:
        segment = fp.read(n)
        if segment == "":
            raise MalformedNetstringError
        n -= len(segment)
        result += segment
    if fp.read(1) != ",":
        raise MalformedNetstringError
    return result


def write_netstring(fp: io.TextIOWrapper, response: str):
    fp.write(f"{len(response)}:{response},")
    fp.flush()


def process_local(local_part: str, cfg: Mapping[str, str]) -> str:
    delimiter = cfg.get("recipient_delimiter", "").strip()
    if delimiter != "":
        local_part = local_part.split(delimiter, 1)[0]
    return local_part.lower()


def split(arg: str, cfg: Mapping[str, str]) -> List[str]:
    parts = arg.split("@", 1)
    parts[0] = process_local(parts[0], cfg)
    parts[1] = parts[1].lower()
    return parts


def parse_config(fp: io.TextIOWrapper) -> Cfg:
    transforms = {
        "all": lambda arg, cfg: [arg],
        "lowercase": lambda arg, cfg: [arg.lower()],
        "local": lambda arg, cfg: [process_local(arg.split("@", 1)[0], cfg)],
        "domain": lambda arg, cfg: [arg.split("@", 1)[1].lower()],
        "split": split,
    }

    cp = configparser.ConfigParser(interpolation=None)
    cp.read_file(fp)

    tables = {}
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

            tables[table_name] = TableCfg(
                query=cp.get(section, "query"),
                transform=transform,
            )

    return Cfg(
        database=dict(cp.items("database")),
        tables=tables,
        misc=dict(cp.items("misc")),
    )


def get_int(cfg: Mapping[str, str], key: str) -> Optional[int]:
    return int(cfg[key]) if key in cfg else None


def serve_client(
    fh_in: io.TextIOWrapper,
    fh_out: io.TextIOWrapper,
    conn,
    timeout: int,
    tables: Mapping[str, TableCfg],
    cfg: Mapping[str, str],
):
    max_requests = get_int(cfg, "max_requests")
    try:
        while True:
            if max_requests is not None:
                max_requests -= 1
                if max_requests < 1:
                    break

            # Wait a short period before exiting.
            iready, _, _ = select.select([fh_in], (), (), timeout)
            if len(iready) == 0:
                break

            request = read_netstring(fh_in)
            if request is None:
                break

            table_name, arg = request.split(" ", 1)

            table = tables.get(table_name)
            if table is None:
                write_netstring(fh_out, f"PERM no such table: {table_name}")
                break

            cur = conn.cursor()
            try:
                cur.execute(table.query, table.transform(arg, cfg))
                result = cur.fetchone()
            finally:
                cur.close()

            if result is None:
                write_netstring(fh_out, "NOTFOUND ")
            else:
                write_netstring(fh_out, f"OK {str(result[0])}")
    except MalformedNetstringError:
        write_netstring(fh_out, "PERM malformed netstring")
    except Exception as exc:
        write_netstring(fh_out, f"PERM {str(exc)}")


def connect(settings: Dict[str, str]):
    """
    Connect to a database.
    """
    driver = importlib.import_module(settings.pop("driver", "sqlite3"))
    return driver.connect(**settings)


def make_parser() -> argparse.ArgumentParser:
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
        default=5,
    )
    parser.add_argument(
        "--client",
        action="store_true",
        help="Start with a debug client",
    )
    return parser


def main():
    args = make_parser().parse_args()

    with contextlib.closing(args.config):
        cfg = parse_config(args.config)

    if args.client:
        svr_args = [arg for arg in sys.argv if arg != "--client"]
        svr_args[0] = os.path.abspath(svr_args[0])
        proc = subprocess.Popen(
            svr_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            encoding="utf-8",
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
                sys.stdin,
                sys.stdout,
                conn,
                args.timeout,
                cfg["tables"],
                cfg["misc"],
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

# vim:set ft=python et:
