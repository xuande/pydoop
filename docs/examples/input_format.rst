.. _input_format_example:

Writing a Custom InputFormat
============================

You can use a custom Java ``InputFormat`` together with a Python
:class:`~pydoop.mapreduce.api.RecordReader`: the java RecordReader
supplied by the ``InputFormat`` will be overridden by the Python one.

Consider the following simple modification of Hadoop's built-in
``TextInputFormat``:

.. code-block:: java

  package it.crs4.pydoop.mapreduce;

  import org.apache.hadoop.fs.Path;
  import org.apache.hadoop.io.LongWritable;
  import org.apache.hadoop.io.Text;
  import org.apache.hadoop.mapreduce.InputSplit;
  import org.apache.hadoop.mapreduce.JobContext;
  import org.apache.hadoop.mapreduce.RecordReader;
  import org.apache.hadoop.mapreduce.TaskAttemptContext;
  import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
  import org.apache.hadoop.mapreduce.lib.input.LineRecordReader;

  public class TextInputFormat extends FileInputFormat<LongWritable, Text> {

      @Override
      public RecordReader<LongWritable, Text> createRecordReader(
        InputSplit split, TaskAttemptContext context) {
          return new LineRecordReader();
      }

      @Override
      protected boolean isSplitable(JobContext context, Path file) {
        return context.getConfiguration().getBoolean(
          "pydoop.input.issplitable", true);
      }
  }

With respect to the default one, this InputFormat adds a configurable
boolean parameter (``pydoop.input.issplitable``) that, if set to
``false``, makes input files non-splitable (i.e., you can't get more
input splits than the number of input files).

For details on how to compile the above code into a jar and use it
with Pydoop, see ``examples/input_format``\ .
