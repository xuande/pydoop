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

import os
import shutil
import tempfile

from pydoop.mapreduce.simulator import HadoopSimulatorNetwork
from pydoop.mapreduce.pipes import InputSplit
import pydoop.test_support as pts

WD = tempfile.mkdtemp(prefix="pydoop_")


def cp_script(script):
    dest = os.path.join(WD, os.path.basename(script))
    with open(script) as f, open(dest, "w") as fo:
        fo.write(pts.set_python_cmd(f.read()))
    os.chmod(dest, 0o755)
    return dest


def main():
    shutil.copy('../schemas/stats.avsc', 'stats.avsc')
    program_name = cp_script('./avro_pyrw.py')
    data_in = './users.avro'
    path = os.path.realpath(data_in)
    length = os.stat(path).st_size
    input_split = InputSplit.to_string('file://' + path, 0, length)
    out_path = os.path.realpath('.')
    conf = {
        "mapreduce.task.partition": "0",
        "mapreduce.task.output.dir": 'file://%s' % out_path,
    }
    hsn = HadoopSimulatorNetwork(program=program_name)
    hsn.run(None, None, conf, input_split=input_split)


if __name__ == '__main__':
    main()
