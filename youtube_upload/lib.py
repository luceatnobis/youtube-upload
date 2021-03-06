#!/usr/bin/env python

import re
import os
import sys
import locale
import random
import time
import signal
from contextlib import contextmanager

from string import (
    ascii_letters as al,
    digits as dig
)

try:  # python3
    from urllib.parse import urlparse, parse_qs
except ImportError:  # python2
    from urlparse import urlparse, parse_qs

@contextmanager
def default_sigint():
    original_sigint_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, original_sigint_handler)


def to_utf8(s):
    """Re-encode string from the default system encoding to UTF-8."""
    current = locale.getpreferredencoding()
    if hasattr(s, 'decode'):  # Python 3 workaround
        return s.decode(
            current).encode("UTF-8") if s and current != "UTF-8" else s
    else:
        if isinstance(s, bytes):
            s = bytes.decode(s)
        return s


def debug(obj, fd=sys.stderr):
    """Write obj to standard error."""
    try:
        unicode
    except NameError:
        unicode = bytes
    string = str(obj.encode(get_encoding(fd), "backslashreplace").decode()
                 if not isinstance(obj, unicode) else obj)
    fd.write(string + "\n")


def catch_exceptions(exit_codes, fun, *args, **kwargs):
    """
    Catch exceptions on fun(*args, **kwargs) and return the exit code specified
    in the exit_codes dictionary. Return 0 if no exception is raised.
    """
    try:
        fun(*args, **kwargs)
        return 0
    except tuple(exit_codes.keys()) as exc:
        debug("[%s] %s" % (exc.__class__.__name__, exc))
        return exit_codes[exc.__class__]


def get_encoding(fd):
    """Guess terminal encoding."""
    return fd.encoding or locale.getpreferredencoding()


def first(it):
    """Return first element in iterable."""
    return it.next()


def string_to_dict(string):
    """Return dictionary from string "key1=value1, key2=value2"."""
    if string:
        pairs = [s.strip() for s in string.split(",")]
        return dict(pair.split("=") for pair in pairs)


def get_first_existing_filename(prefixes, relative_path):
    import pdb
    """Get the first existing filename of """
    """relative path seeking on prefixes directories."""
    for prefix in prefixes:
        path = os.path.join(prefix, relative_path)
        if os.path.exists(path):
            return path

def get_standard_filename(fname):
    filenames = [
        os.path.join(os.getcwd(), fname),
        os.path.join(os.path.expanduser("~"), fname)
    ]
    for x in filenames:
        if not os.path.exists(x):
            continue
        return x
    return get_first_existing_filename(
        [sys.prefix, os.path.join(sys.prefix, "local")],
        "share/youtube_upload/client_secrets.json")

def retriable_exceptions(fun, retriable_exceptions, max_retries=None):
    """Run function and retry on some exceptions (with exponential backoff)."""
    retry = 0
    while 1:
        try:
            return fun()
        except tuple(retriable_exceptions) as exc:
            retry += 1
            if type(exc) not in retriable_exceptions:
                raise exc
            elif max_retries is not None and retry > max_retries:
                debug("[Retryable errors] Retry limit reached")
                raise exc
            else:
                foo = "{error_type} ({error_msg}). Wait {wait_time} seconds"
                seconds = random.uniform(0, 2**retry)
                message = (
                    "[Retryable error {current_retry}/{total_retries}] " +
                    foo).format(
                    current_retry=retry,
                    total_retries=max_retries or "-",
                    error_type=type(exc).__name__,
                    error_msg=str(exc) or "-",
                    wait_time="%.1f" % seconds,
                )
                debug(message)
                time.sleep(seconds)

def extract_vid_from_file(f):
    collection = list()
    try:
        c = open(f)
        lines = [x.rstrip() for x in c.readlines()]
        c.close()
    except IOError:
        print(
            "Could not open \"%s\"; skipping" % f, file=sys.stderr)
        return
    for l in lines:
        v = filter_vid(l)
        if not v:
            continue
        collection.append(v)
    return collection

def filter_vid(line):
    p = urlparse(line)
    if p.scheme:
        v = parse_qs(p.query)
        if not 'v' in v:
            return False
        vid = v['v'][0]
    else:
        vid = line
    return vid if check_valid_id(vid) else None

def extract_vid_from_cli(vid, delimiters=[',', ', '], extra_delim=[]):
    ids = list()
    ids.extend(re.split('|'.join(delimiters + extra_delim), vid))
    return ids

def check_valid_id(vid):
    vid_chars = set(al + dig + "".join(["-", "_"]))
    s = set(list(vid))
    # checks if all chars of vid are allowed
    return len(vid) == 11 and s & vid_chars == s
