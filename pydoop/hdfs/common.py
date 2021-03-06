# BEGIN_COPYRIGHT
#
# Copyright 2009-2017 CRS4.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# END_COPYRIGHT

"""
Common hdfs utilities.
"""

import getpass
import pwd
import grp
import sys
import os

__is_py3 = sys.version_info >= (3, 0)


BUFSIZE = 16384
DEFAULT_PORT = 8020  # org/apache/hadoop/hdfs/server/namenode/NameNode.java
DEFAULT_USER = getpass.getuser()
DEFAULT_LIBHDFS_OPTS = "-Xmx48m"  # enough for most applications

# Unicode objects are encoded using this encoding:
TEXT_ENCODING = 'utf-8'
# We use UTF-8 since this is what the Hadoop TextFileFormat uses
# NOTE:  If you change this, you'll also need to fix the encoding
# used by the native extension.


class Mode(object):
    """\
    File opening mode.

    Supported mode strings are limited to ``'rb', 'wb', 'ab'`` (or simply
    ``'r', 'w', 'a'``) for binary mode and ``'rt', 'wt', 'at'`` for text
    mode. Semantics are similar to :func:`io.open`, but note that the default
    mode is binary.

    For backwards compatibility, the constructor also accepts
    :data:`os.O_RDONLY`, :data:`os.O_WRONLY` and :data:`os.O_WRONLY` |
    :data:`os.O_APPEND`, respectively equivalent to ``'rb', 'wb'`` and
    ``'ab'``.
    """

    VALUE = {
        "r": os.O_RDONLY,
        "w": os.O_WRONLY,
        "a": os.O_WRONLY | os.O_APPEND,
    }

    FLAGS = {
        os.O_RDONLY: "r",
        os.O_WRONLY: "w",
        os.O_WRONLY | os.O_APPEND: "a",
    }

    @property
    def value(self):
        return self.__value

    @property
    def flags(self):
        return self.__flags

    @property
    def text(self):
        return self.__text

    @property
    def binary(self):
        return not self.__text

    @property
    def writable(self):
        return self.flags & os.O_WRONLY

    def __init__(self, m=None):
        if isinstance(m, self.__class__):
            self.__value = m.value
            self.__flags = m.flags
            self.__text = m.text
            return
        else:
            self.__value = "rb"
            self.__flags = os.O_RDONLY
            self.__text = False
        if not m:
            return
        try:
            self.__value = m[0]
        except TypeError:
            try:
                self.__value = Mode.FLAGS[m]
            except KeyError:
                self.__error(m)
            else:
                self.__flags = m
        else:
            try:
                self.__flags = Mode.VALUE[self.__value]
            except KeyError:
                self.__error(m)
            else:
                try:
                    self.__text = m[1] == "t"
                except IndexError:
                    pass
        self.__value += 't' if self.__text else 'b'

    def __error(self, m):
        raise ValueError("invalid mode: %r" % (m,))

    def __eq__(self, m):
        try:
            return self.__class__(m).value == self.value
        except ValueError:
            return False

    def __ne__(self, m):
        return not self.__eq__(m)

    def __str__(self):
        return self.__value

    @classmethod
    def copy(cls, m):
        return cls(m)


if __is_py3:
    def encode_path(path):
        return path

    def decode_path(path):
        return path

    def encode_host(host):
        return host

    def decode_host(host):
        return host
else:
    def encode_path(path):
        if isinstance(path, unicode):  # noqa: F821
            path = path.encode('utf-8')
        return path

    def decode_path(path):
        if isinstance(path, str):
            path = path.decode('utf-8')
        return path

    def encode_host(host):
        if isinstance(host, unicode):  # noqa: F821
            host = host.encode('idna')
        return host

    def decode_host(host):
        if isinstance(host, str):
            host = host.decode('idna')
        return host


def get_groups(user=DEFAULT_USER):
    groups = set(_.gr_name for _ in grp.getgrall() if user in set(_.gr_mem))
    primary_gid = pwd.getpwnam(user).pw_gid
    groups.add(grp.getgrgid(primary_gid).gr_name)
    return groups
