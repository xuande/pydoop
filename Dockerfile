FROM crs4/hadoop
MAINTAINER simone.leo@crs4.it

RUN yum install https://centos7.iuscommunity.org/ius-release.rpm
RUN curl https://bintray.com/sbt/rpm/rpm -o /etc/yum.repos.d/bintray-sbt-rpm.repo

# needed only to run examples: zip, wheel, sbt
# needed TEMPORARILY: bc (https://github.com/sbt/sbt-launcher-package/pull/191)
RUN yum install \
    bc \
    gcc \
    gcc-c++ \
    python-devel \
    python-pip \
    python36u-devel \
    python36u-pip \
    sbt \
    zip
RUN ln -rs /usr/bin/python3.6 /usr/bin/python3 && \
    ln -rs /usr/bin/pip3.6 /usr/bin/pip3

ENV HADOOP_HOME /opt/hadoop
ENV LC_ALL en_US.UTF-8
ENV LANG en_US.UTF-8

COPY . /build/pydoop
WORKDIR /build/pydoop

RUN source /etc/profile && for v in 2 3; do \
      pip${v} install --upgrade pip && \
      pip${v} install --upgrade -r requirements.txt && \
      python${v} setup.py build && \
      python${v} setup.py install --skip-build; \
    done
