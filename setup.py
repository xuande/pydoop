import sys, os, platform, re
from distutils.core import setup, Extension


# JAVA_HOME=my/java/home HADOOP_HOME=my/hadoop/home python setup.py build
JAVA_HOME = os.getenv("JAVA_HOME") or "/opt/sun-jdk"
HADOOP_HOME = os.getenv("HADOOP_HOME") or "/opt/hadoop"


def get_arch():
    bits, linkage = platform.architecture()
    if bits == "64bit":
        return "amd64", "64"
    return "i386", "32"


def get_java_include_dirs(java_home):
    p = platform.system().lower()  # TODO: test for non-linux
    java_inc = os.path.join(java_home, "include")
    java_platform_inc = "%s/%s" % (java_inc, p)
    return [java_inc, java_platform_inc]


def get_hadoop_include_dirs(hadoop_home):
    a = "-".join(get_arch())
    return [os.path.join(hadoop_home, "c++/Linux-%s/include" % a)]


def get_java_library_dirs(java_home):
    a = get_arch()[0]
    return [os.path.join(java_home, "jre/lib/%s/server" % a)]


class BoostExtFactory(object):

    export_pattern = re.compile(r"void\s+export_(\w+)")

    def __init__(self, name, wrap_files, aux_files, **ext_args):
        self.name = name
        self.wrap_files = wrap_files
        self.aux_files = aux_files
        self.main = self.__generate_main()
        self.ext_args = ext_args

    def __generate_main(self):
        sys.stderr.write("generating main for %s...\n" % self.name)
        first_half = ["#include <boost/python.hpp>"]
        second_half = ["BOOST_PYTHON_MODULE(%s){" % self.name]
        for fn in self.wrap_files:
            f = open(fn)
            code = f.read()
            f.close()
            m = self.export_pattern.search(code)
            if m is not None:
                fun_name = "export_%s" % m.groups()[0]
                first_half.append("void %s();" % fun_name)
                second_half.append("%s();" % fun_name)
        second_half.append("}")
        destdir = os.path.split(self.wrap_files[0])[0]  # should be fine
        outfn = os.path.join(destdir, "%s_main.cpp" % self.name)
        outf = open(outfn, "w")
        for line in first_half:
            outf.write("%s%s" % (line, os.linesep))
        for line in second_half:
            outf.write("%s%s" % (line, os.linesep))
        outf.close()
        return outfn

    def create(self):
        all_files = self.aux_files + self.wrap_files + [self.main]
        return Extension(self.name, all_files, **self.ext_args)


def create_pipes_ext():
    wrap = ["pipes", "pipes_context", "pipes_test_support",
            "pipes_serial_utils", "exceptions"]
    aux = ["HadoopPipes", "SerialUtils", "StringUtils"]
    factory = BoostExtFactory(
        "pydoop_pipes",
        ["src/%s.cpp" % n for n in wrap],
        ["src/%s.cpp" % n for n in aux],
        include_dirs=get_hadoop_include_dirs(HADOOP_HOME),
        libraries = ["pthread", "boost_python"],
        )
    return factory.create()


def create_hdfs_ext():
    wrap = ["hdfs_fs", "hdfs_file", "hdfs_common"]
    aux = []
    library_dirs = get_java_library_dirs(JAVA_HOME) + [
            os.path.join(HADOOP_HOME, "c++/Linux-%s-%s/lib" % get_arch())]
    factory = BoostExtFactory(
        "pydoop_hdfs",
        ["src/%s.cpp" % n for n in wrap],
        ["src/%s.cpp" % n for n in aux],
        include_dirs=get_java_include_dirs(JAVA_HOME) + [
            os.path.join(HADOOP_HOME, "src/c++/libhdfs")],
        library_dirs=library_dirs,
        runtime_library_dirs=library_dirs,
        libraries=["pthread", "boost_python", "hdfs", "jvm"],
        )
    return factory.create()


def create_ext_modules():
    ext_modules = []
    ext_modules.append(create_pipes_ext())
    ext_modules.append(create_hdfs_ext())
    return ext_modules


setup(
    name="pydoop",
    version="0.2.6",
    description="Python MapReduce API for Hadoop",
    author="Gianluigi Zanetti",
    author_email="<gianluigi.zanetti@crs4.it>",
    maintainer="Simone Leo",
    maintainer_email="simleo@crs4.it",
    url="http://svn.crs4.it/ac-dc/lib/pydoop",
    packages=["pydoop"],
    ext_modules=create_ext_modules()
    )
