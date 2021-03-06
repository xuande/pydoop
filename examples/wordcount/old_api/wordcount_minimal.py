#!/usr/bin/env python

# BEGIN_COPYRIGHT
#
# Copyright 2009-2017 CRS4.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# END_COPYRIGHT

"""
This example includes only the bare minimum required to run
wordcount. See wordcount-full.py for an example that uses counters,
RecordReader, etc.
"""

from __future__ import print_function
import pydoop.pipes as pp
import re


class Mapper(pp.Mapper):

    def map(self, context):
        words = re.sub(b'[^0-9a-zA-Z]+', b' ', context.getInputValue()).split()
        for w in words:
            context.emit(w, b'1')


class Reducer(pp.Reducer):

    def reduce(self, context):
        s = 0
        while context.nextValue():
            s += int(context.getInputValue())
        context.emit(context.getInputKey(), str(s).encode("utf8"))


if __name__ == "__main__":
    pp.runTask(pp.Factory(mapper_class=Mapper, reducer_class=Reducer))
