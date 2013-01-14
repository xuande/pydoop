# BEGIN_COPYRIGHT
# 
# Copyright 2009-2013 CRS4.
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
Important environment variables
-------------------------------

The Pydoop setup looks in a number of default paths for what it
needs.  If necessary, you can override its behaviour or provide an
alternative path by exporting the environment variables below::

  JAVA_HOME, e.g., /opt/sun-jdk
  HADOOP_HOME, e.g., /opt/hadoop-1.0.2

Other relevant environment variables include::

  BOOST_PYTHON: name of the Boost.Python library, with the leading 'lib'
    and the trailing extension stripped. Defaults to 'boost_python'.
  HADOOP_VERSION, e.g., 0.20.2-cdh3u4 (override Hadoop's version string).
"""

import os, platform, re, glob, shutil, itertools
from distutils.core import setup
from distutils.extension import Extension
from distutils.command.build_ext import build_ext
from distutils.command.build_py import build_py
from distutils.command.clean import clean
from distutils.errors import DistutilsSetupError
from distutils import log

import pydoop
import pydoop.hadoop_utils as hu


try:
  JAVA_HOME = os.environ["JAVA_HOME"]
except KeyError:
  raise RuntimeError("java home not found, try setting JAVA_HOME")
HADOOP_HOME = pydoop.hadoop_home(fallback=None)
SYSTEM = platform.system().lower()
HADOOP_VERSION_INFO = pydoop.hadoop_version_info()
BOOST_PYTHON = os.getenv("BOOST_PYTHON", "boost_python")
PIPES_SRC = ["src/%s.cpp" % n for n in (
  "pipes",
  "pipes_context",
  "pipes_test_support",
  "pipes_serial_utils",
  "exceptions",
  "pipes_input_split",
  )]
HDFS_SRC = ["src/%s.cpp" % n for n in (
  "hdfs_fs",
  "hdfs_file",
  "hdfs_common",
  )]


# ---------
# UTILITIES
# ---------

def rm_rf(path, dry_run=False):
  """
  Remove a file or directory tree.

  Won't throw an exception, even if the removal fails.
  """
  log.info("removing %s" % path)
  if dry_run:
    return
  try:
    if os.path.isdir(path) and not os.path.islink(path):
      shutil.rmtree(path)
    else:
      os.remove(path)
  except OSError:
    pass


def get_arch():
  if SYSTEM == 'darwin':
    return "", ""
  bits, _ = platform.architecture()
  if bits == "64bit":
    return "amd64", "64"
  return "i386", "32"


def get_java_include_dirs(java_home):
  java_inc = os.path.join(java_home, "include")
  java_platform_inc = "%s/%s" % (java_inc, SYSTEM)
  return [java_inc, java_platform_inc]


def get_java_library_dirs(java_home):
  a = get_arch()[0]
  return [os.path.join(java_home, "jre/lib", a, "server")]


def mtime(fn):
  return os.stat(fn).st_mtime


def must_generate(target, prerequisites):
  try:
    return max(mtime(p) for p in prerequisites) > mtime(target)
  except OSError:
    return True


def get_version_string(filename="VERSION"):
  try:
    with open(filename) as f:
      return f.read().strip()
  except IOError:
    raise DistutilsSetupError("failed to read version info")


def write_config(filename="pydoop/config.py"):
  prereq = "DEFAULT_HADOOP_HOME"
  if not os.path.exists(prereq):
    with open(prereq, "w") as f:
      f.write("%s\n" % HADOOP_HOME)
  if must_generate(filename, [prereq]):
    with open(filename, "w") as f:
      f.write("# GENERATED BY setup.py\n")
      f.write("DEFAULT_HADOOP_HOME='%s'\n" % HADOOP_HOME)


def write_version(filename="pydoop/version.py"):
  prereq = "VERSION"
  if must_generate(filename, [prereq]):
    version = get_version_string(filename=prereq)
    with open(filename, "w") as f:
      f.write("# GENERATED BY setup.py\n")
      f.write("version='%s'\n" % version)


def get_hdfs_macros(hdfs_hdr):
  """
  Search libhdfs headers for specific features.
  """
  hdfs_macros = []
  with open(hdfs_hdr) as f:
    t = f.read()
  delete_args = re.search(r"hdfsDelete\((.+)\)", t).groups()[0].split(",")
  cas_args = re.search(r"hdfsConnectAsUser\((.+)\)", t).groups()[0].split(",")
  ## cas_newinst = bool(re.search(r"hdfsConnectAsUserNewInstance\((.+)\)", t))
  ## c_newinst = bool(re.search(r"hdfsConnectNewInstance\((.+)\)", t))
  ## hflush = bool(re.search(r"hdfsHFlush\((.+)\)", t))
  if len(delete_args) > 2:
    hdfs_macros.append(("RECURSIVE_DELETE", None))
  if len(cas_args) > 3:
    hdfs_macros.append(("CONNECT_GROUP_INFO", None))
  ## if cas_newinst:
  ##   hdfs_macros.append(("CONNECT_AS_USER_NEW_INST", None))
  ## if c_newinst:
  ##   hdfs_macros.append(("CONNECT_NEW_INST", None))
  ## if hflush:
  ##   hdfs_macros.append(("HFLUSH", None))
  return hdfs_macros


def have_better_tls():
  """
  See ${HADOOP_HOME}/hadoop-hdfs-project/hadoop-hdfs/src/CMakeLists.txt
  """
  return False  # FIXME: need a portable implementation


# ------------
# BUILD ENGINE
# ------------

class HadoopSourcePatcher(object):

  def __init__(self, hadoop_version_info=HADOOP_VERSION_INFO):
    self.hadoop_version_info = hadoop_version_info
    self.hadoop_tag = "hadoop-%s" % self.hadoop_version_info
    self.patch_fn = "patches/%s.patch" % self.hadoop_tag
    self.src_dir = "src/%s" % self.hadoop_tag
    self.patched_src_dir = "%s.patched" % self.src_dir
    self.from_jtree = os.path.join(
      self.patched_src_dir, "org/apache/hadoop/mapred/pipes"
      )
    self.to_jtree = os.path.join(
      self.patched_src_dir, "it/crs4/pydoop/pipes"
      )

  def __link_closest_tag(self):
    available, cmp_attr = self.__get_available_versions()
    closest_vinfo = self.__get_closest_version(available, cmp_attr)
    if closest_vinfo is None:
      raise RuntimeError(
        "none of the supported versions is close enough to %s" %
        self.hadoop_version_info
        )
    closest_tag = "hadoop-%s" % closest_vinfo
    old_wd = os.getcwd()
    os.chdir("src")
    os.symlink(closest_tag, self.hadoop_tag)
    os.chdir("../patches")
    os.symlink("%s.patch" % closest_tag, "%s.patch" % self.hadoop_tag)
    os.chdir(old_wd)
    return closest_tag

  def __get_available_versions(self):
    pattern = re.compile(r"^hadoop-.+\d$")
    available = [
      hu.HadoopVersion(fn.split("-", 1)[1])
      for fn in os.listdir("src")
      if pattern.match(fn)
      ]
    if self.hadoop_version_info.is_cloudera():
      available = [vinfo for vinfo in available if (
        vinfo.is_cloudera() and
        vinfo.main == self.hadoop_version_info.main and
        vinfo.ext == self.hadoop_version_info.ext
        )]
      cmp_attr = "cdh"
    else:
      available = [vinfo for vinfo in available if not vinfo.is_cloudera()]
      cmp_attr = "main"
    return available, cmp_attr

  def __get_closest_version(self, available, cmp_attr):
    vkey = getattr(self.hadoop_version_info, cmp_attr)
    candidate_map = {}
    for vinfo in available:
      k = getattr(vinfo, cmp_attr)
      if len(k) == len(vkey):
        candidate_map[k] = vinfo
    for i in xrange(-1, -len(vkey), -1):
      selection = [
        (abs(k[i]-vkey[i]), vinfo)
        for (k, vinfo) in candidate_map.iteritems()
        if k[:i] == vkey[:i]
        ]
      if selection:
        return min(selection)[1]

  def __generate_hdfs_config(self):
    """
    Generate config.h for libhdfs.

    This is only relevant for recent Hadoop versions.
    """
    config_fn = os.path.join(self.patched_src_dir, "libhdfs", "config.h")
    with open(config_fn, "w") as f:
      f.write("#ifndef CONFIG_H\n#define CONFIG_H\n")
      if have_better_tls():
        f.write("#define HAVE_BETTER_TLS\n")
      f.write("#endif\n")

  def __convert_pkg(self):
    assert os.path.isdir(self.from_jtree)
    os.makedirs(self.to_jtree)
    for bn in os.listdir(self.from_jtree):
      with open(os.path.join(self.from_jtree, bn)) as f:
        content = f.read()
      with open(os.path.join(self.to_jtree, bn), "w") as f:
        f.write(content.replace(
          "org.apache.hadoop.mapred.pipes", " it.crs4.pydoop.pipes"
          ))

  def patch(self):
    if not os.path.isdir(self.src_dir):
      closest_tag = self.__link_closest_tag()
      assert os.path.isfile(self.patch_fn)
      log.warn("*** WARNING: %s NOT SUPPORTED, TRYING %s ***" % (
        self.hadoop_tag, closest_tag
        ))
    if must_generate(self.patched_src_dir, [self.src_dir, self.patch_fn]):
      log.info("patching source code %r" % (self.src_dir,))
      shutil.rmtree(self.patched_src_dir, ignore_errors=True)
      shutil.copytree(self.src_dir, self.patched_src_dir)
      cmd = "patch -d %s -N -p1 < %s" % (self.patched_src_dir, self.patch_fn)
      if os.system(cmd):
        raise DistutilsSetupError("Error applying patch.  Command: %s" % cmd)
      self.__generate_hdfs_config()
      self.__convert_pkg()
    return self.patched_src_dir


class BoostExtension(Extension):
  """
  Customized Extension class that generates the necessary Boost.Python
  export code.
  """
  export_pattern = re.compile(r"void\s+export_(\w+)")

  def __init__(self, name, wrap_sources, aux_sources, **kw):
    Extension.__init__(self, name, wrap_sources+aux_sources, **kw)
    self.module_name = self.name.split(".", 1)[-1]
    self.wrap_sources = wrap_sources

  def generate_main(self):
    destdir = os.path.split(self.wrap_sources[0])[0]  # should be ok
    outfn = os.path.join(destdir, "%s_main.cpp" % self.module_name)
    if must_generate(outfn, self.wrap_sources):
      log.debug("generating main for %s\n" % self.name)
      first_half = ["#include <boost/python.hpp>"]
      second_half = ["BOOST_PYTHON_MODULE(%s){" % self.module_name]
      for fn in self.wrap_sources:
        with open(fn) as f:
          code = f.read()
        m = self.export_pattern.search(code)
        if m is not None:
          fun_name = "export_%s" % m.groups()[0]
          first_half.append("void %s();" % fun_name)
          second_half.append("%s();" % fun_name)
      second_half.append("}")
      with open(outfn, "w") as outf:
        for line in first_half:
          outf.write("%s%s" % (line, os.linesep))
        for line in second_half:
          outf.write("%s%s" % (line, os.linesep))
    return outfn


def create_pipes_ext(patched_src_dir, pipes_ext_name):
  include_dirs = [
    "%s/%s/api" % (patched_src_dir, _) for _ in "pipes", "utils"
    ]
  libraries = ["pthread", BOOST_PYTHON]
  if HADOOP_VERSION_INFO.tuple != (0, 20, 2):
    libraries.append("ssl")
  return BoostExtension(
    pipes_ext_name,
    PIPES_SRC,
    glob.glob("%s/*/impl/*.cc" % patched_src_dir),
    include_dirs=include_dirs,
    libraries=libraries
    )


def create_hdfs_ext(patched_src_dir, hdfs_ext_name):
  java_include_dirs = get_java_include_dirs(JAVA_HOME)
  log.info("java_include_dirs: %r" % (java_include_dirs,))
  include_dirs = java_include_dirs + ["%s/libhdfs" % patched_src_dir]
  java_library_dirs = get_java_library_dirs(JAVA_HOME)
  log.info("java_library_dirs: %r" % (java_library_dirs,))
  return BoostExtension(
    hdfs_ext_name,
    HDFS_SRC,
    glob.glob("%s/libhdfs/*.c" % patched_src_dir),
    include_dirs=include_dirs,
    library_dirs=java_library_dirs,
    runtime_library_dirs=java_library_dirs,
    libraries=["pthread", BOOST_PYTHON, "jvm"],
    define_macros=get_hdfs_macros(
      os.path.join(patched_src_dir, "libhdfs", "hdfs.h")
      ),
    )


class JavaLib(object):

  def __init__(self, hadoop_vinfo, pipes_src_dir):
    self.hadoop_vinfo = hadoop_vinfo
    self.jar_name = pydoop.jar_name(self.hadoop_vinfo)
    self.classpath = pydoop.hadoop_classpath()
    if not self.classpath:
      log.warn("could not set classpath, java code may not compile")
    self.java_files = ["src/it/crs4/pydoop/NoSeparatorTextOutputFormat.java"]
    if self.hadoop_vinfo.has_security():
      if hadoop_vinfo.cdh >= (4, 0, 0) and not hadoop_vinfo.ext:
        return  # TODO: add support for mrv2
      # add our fix for https://issues.apache.org/jira/browse/MAPREDUCE-4000
      self.java_files.extend(glob.glob("%s/*" % pipes_src_dir))


class ExtensionManager(object):

  PIPES_EXT_BASENAME = "_pipes"
  HDFS_EXT_BASENAME = "_hdfs"

  def __init__(self):
    self.mr1_vinfo = None
    self.pipes_mr1_ext_name = None
    self.hdfs_mr1_ext_name = None
    self.mr1_patcher = None
    #--
    self.pipes_ext_name = pydoop.complete_mod_name(
      self.PIPES_EXT_BASENAME, hadoop_vinfo=HADOOP_VERSION_INFO
      )
    self.hdfs_ext_name = pydoop.complete_mod_name(
      self.HDFS_EXT_BASENAME, hadoop_vinfo=HADOOP_VERSION_INFO
      )
    self.patcher = HadoopSourcePatcher(HADOOP_VERSION_INFO)
    #--
    if HADOOP_VERSION_INFO.cdh >= (4, 0, 0):
      self.mr1_vinfo = hu.cdh_mr1_version(HADOOP_VERSION_INFO)
      self.pipes_mr1_ext_name = pydoop.complete_mod_name(
        self.PIPES_EXT_BASENAME, hadoop_vinfo=self.mr1_vinfo
        )
      self.hdfs_mr1_ext_name = pydoop.complete_mod_name(
        self.HDFS_EXT_BASENAME, hadoop_vinfo=self.mr1_vinfo
        )
      self.mr1_patcher = HadoopSourcePatcher(self.mr1_vinfo)
    #--
    self.patched_src_dir = None
    self.patched_java_src_dir = None
    self.mr1_patched_src_dir = None
    self.mr1_patched_java_src_dir = None

  def patch_src(self):
    self.patched_src_dir = self.patcher.patch()
    self.patched_java_src_dir = self.patcher.to_jtree
    if self.mr1_vinfo:
      self.mr1_patched_src_dir = self.mr1_patcher.patch()
      self.mr1_patched_java_src_dir = self.mr1_patcher.to_jtree

  def create_pipes_extensions(self):
    extensions = [create_pipes_ext(self.patched_src_dir, self.pipes_ext_name)]
    if self.mr1_vinfo:
      extensions.append(create_pipes_ext(
        self.mr1_patched_src_dir, self.pipes_mr1_ext_name
        ))
    for e in extensions:
      e.sources.append(e.generate_main())
    return extensions

  def create_hdfs_extensions(self):
    extensions = [create_hdfs_ext(self.patched_src_dir, self.hdfs_ext_name)]
    if self.mr1_vinfo:
      extensions.append(create_hdfs_ext(
        # NOT a bug: we want non-mr1 code with a _mr1 suffix in the ext name
        self.patched_src_dir, self.hdfs_mr1_ext_name
        ))
    for e in extensions:
      e.sources.append(e.generate_main())
    return extensions

  def create_extensions(self):
    return self.create_pipes_extensions() + self.create_hdfs_extensions()

  def create_java_libs(self):
    java_libs = [JavaLib(HADOOP_VERSION_INFO, self.patched_java_src_dir)]
    if self.mr1_vinfo:
      java_libs.append(JavaLib(self.mr1_vinfo, self.mr1_patched_java_src_dir))
    return java_libs


class BuildExt(build_ext):

  EXT_MANAGER = ExtensionManager()

  def finalize_options(self):
    build_ext.finalize_options(self)
    self.EXT_MANAGER.patch_src()
    self.extensions = self.EXT_MANAGER.create_extensions()
    self.java_libs = self.EXT_MANAGER.create_java_libs()

  def build_extension(self, ext):
    try:
      self.compiler.compiler_so.remove("-Wstrict-prototypes")
      if SYSTEM == 'darwin':
        self.compiler.linker_so.extend(["-rpath", os.path.join(JAVA_HOME, 'jre/lib/server')])
    except ValueError:
      pass
    build_ext.build_extension(self, ext)

  def run(self):
    log.info("hadoop_home: %r" % (HADOOP_HOME,))
    log.info("hadoop_version: '%s'" % HADOOP_VERSION_INFO)
    log.info("java_home: %r" % (JAVA_HOME,))
    build_ext.run(self)
    for jlib in self.java_libs:
      self.__build_java_lib(jlib)

  def __build_java_lib(self, jlib):
    log.info("Building java code for hadoop-%s" % jlib.hadoop_vinfo)
    compile_cmd = "javac -classpath %s" % jlib.classpath
    class_dir = os.path.join(self.build_temp, "pipes-%s" % jlib.hadoop_vinfo)
    package_path = os.path.join(self.build_lib, "pydoop", jlib.jar_name)
    if not os.path.exists(class_dir):
      os.mkdir(class_dir)
    compile_cmd += " -d '%s'" % class_dir
    log.info("Compiling Java classes")
    for f in jlib.java_files:
      compile_cmd += " %s" % f
    log.debug("Command: %s", compile_cmd)
    ret = os.system(compile_cmd)
    if ret:
      raise DistutilsSetupError(
        "Error compiling java component.  Command: %s" % compile_cmd
        )
    package_cmd = "jar -cf %(package_path)s -C %(class_dir)s ./it" % {
      'package_path': package_path, 'class_dir': class_dir
      }
    log.info("Packaging Java classes")
    log.debug("Command: %s", package_cmd)
    ret = os.system(package_cmd)
    if ret:
      raise DistutilsSetupError(
        "Error packaging java component.  Command: %s" % package_cmd
        )


class BuildPy(build_py):

  def run(self):
    write_config()
    write_version()
    build_py.run(self)


class Clean(clean):

  def run(self):
    clean.run(self)
    garbage_list = [
      "DEFAULT_HADOOP_HOME",
      "pydoop/config.py",
      "pydoop/version.py",
    ]
    garbage_list.extend(glob.iglob("src/*.patched"))
    garbage_list.extend(p for p in itertools.chain(
      glob.iglob('src/*'), glob.iglob('patches/*')
      ) if os.path.islink(p))
    garbage_list.extend(glob.iglob('./src/_hdfs_*_main.cpp'))
    garbage_list.extend(glob.iglob('./src/_pipes_*_main.cpp'))
    for p in garbage_list:
      rm_rf(p, self.dry_run)


# Actual ext_modules are created on the fly.  We use a dummy object to:
#   1. Trigger build_ext
#   2. Make egg_info happy (PIP installation)
DUMMY_EXT_MODULES = []
for attr_name in (
  "pipes_ext_name", "hdfs_ext_name", "pipes_mr1_ext_name", "hdfs_mr1_ext_name"
  ):
  attr = getattr(BuildExt.EXT_MANAGER, attr_name)
  if attr is not None:
    DUMMY_EXT_MODULES.append((attr, None))

setup(
  name="pydoop",
  version=get_version_string(),
  description=pydoop.__doc__.strip().splitlines()[0],
  long_description=pydoop.__doc__.lstrip(),
  author=pydoop.__author__,
  author_email=pydoop.__author_email__,
  url=pydoop.__url__,
  download_url="https://sourceforge.net/projects/pydoop/files/",
  packages=[
    "pydoop",
    "pydoop.hdfs",
    "pydoop.app",
    ],
  cmdclass={
    "build_py": BuildPy,
    "build_ext": BuildExt,
    "clean": Clean,
    },
  ext_modules=DUMMY_EXT_MODULES,
  scripts=["scripts/pydoop"],
  platforms=["Linux"],
  license="Apache-2.0",
  keywords=["hadoop", "mapreduce"],
  classifiers=[
    "Programming Language :: Python",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: POSIX :: Linux",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Intended Audience :: Developers",
    ],
  )

# vim: set sw=2 ts=2 et
