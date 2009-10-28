#!/usr/bin/env python

import sys, os, logging
logging.basicConfig(level=logging.DEBUG)

from pydoop.pipes import Mapper, Reducer, Factory, runTask
from pydoop.pipes import RecordReader, InputSplit, RecordWriter
from pydoop.utils import jc_configure, jc_configure_int

from pydoop.hdfs import hdfs
from pydoop.utils import split_hdfs_path


WORDCOUNT = "WORDCOUNT"
INPUT_WORDS = "INPUT_WORDS"
OUTPUT_WORDS = "OUTPUT_WORDS"


class WordCountMapper(Mapper):

  def __init__(self, context):
    super(WordCountMapper, self).__init__(context)
    self.inputWords = context.getCounter(WORDCOUNT, INPUT_WORDS)
  
  def map(self, context):
    words = context.getInputValue().split()
    for w in words:
      context.emit(w, "1")
    context.incrementCounter(self.inputWords, len(words))


class WordCountReducer(Reducer):

  def __init__(self, context):
    super(WordCountReducer, self).__init__(context)
    self.outputWords = context.getCounter(WORDCOUNT, OUTPUT_WORDS)
  
  def reduce(self, context):
    s = 0
    while context.nextValue():
      s += int(context.getInputValue())
    context.emit(context.getInputKey(), str(s))
    context.incrementCounter(self.outputWords, 1)


class WordCountReader(RecordReader):

  def __init__(self, context):
    super(WordCountReader, self).__init__()
    self.logger = logging.getLogger("WordCountReader")
    self.isplit = InputSplit(context.getInputSplit())
    for a in "filename", "offset", "length":
      self.logger.debug("isplit.%s = %r" % (a, getattr(self.isplit, a)))
    self.host, self.port, self.fpath = split_hdfs_path(self.isplit.filename)
    self.fs = hdfs(self.host, self.port)
    self.file = self.fs.open_file(self.fpath, os.O_RDONLY, 0, 0, 0)
    self.logger.debug("readline chunk size = %r" % self.file.chunk_size)
    self.file.seek(self.isplit.offset)
    if self.isplit.offset > 0:
      self.file.readline()  # discard, read by previous reader
    self.bytes_read = 0

  def __del__(self):
    self.file.close()
    self.fs.close()
    
  def next(self):
    if self.bytes_read > self.isplit.length:  # end of input split
      return (False, "", "")
    record = self.file.readline()
    if record == "":  # end of file
      return (False, "", "")
    self.bytes_read += len(record)
    return (True, "dummy", record)

  def getProgress(self):
    return min(float(self.bytes_read)/self.isplit.length, 1.0)


class WordCountWriter(RecordWriter):

  def __init__(self, context):
    super(WordCountWriter, self).__init__(context)
    jc = context.getJobConf()
    jc_configure_int(self, jc, "mapred.task.partition", "part")
    jc_configure(self, jc, "mapred.work.output.dir", "outdir")
    self.outfn = "%s/part-%05d" % (self.outdir, self.part)
    self.host, self.port, self.fpath = split_hdfs_path(self.outfn)
    self.fs = hdfs(self.host, self.port)
    self.file = self.fs.open_file(self.fpath, os.O_WRONLY, 0, 0, 0)

  def __del__(self):
    self.file.close()
    self.fs.close()

  def emit(self, key, value):
    self.file.write("%s\t%s\n" % (key, value))


def main(argv):
  runTask(Factory(WordCountMapper, WordCountReducer,
                  record_reader_class=WordCountReader,
                  record_writer_class=WordCountWriter
                  ))


if __name__ == "__main__":
  main(sys.argv)