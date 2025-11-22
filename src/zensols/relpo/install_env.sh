#!/bin/bash
#@meta {desc: "envdist installer", date: "2025-11-21"}

PROG=$(basename $0)
USAGE="usage: $PROG [prefix] | --help\n
Arguments:\n  prefix  the directory to install (defaults to ./env)\n"


# fail out of the program with an error message
function bail() {
    msg=$1 ; shift
    usage=$1 ; shift
    echo "$PROG: error: $msg" > /dev/stderr
    if [ "$usage" == 1 ] ; then
	printf "${USAGE}" > /dev/stderr
    fi
    exit 1
}

# make sure the last command ran was successful and fail otherwise
function assert_success() {
    ret=$1 ; shift
    if [ $ret -ne 0 ] ; then
	bail "last command failed"
    fi
}

# install the program
function install() {
    prefix=$1 ; shift
    plat="${PROG%-install.sh}"
    env_file="${plat}-environment.yml"
    req_file="${plat}-requirements.txt"
    mkdir -p $prefix
    conda env create -f ${env_file} --prefix="${prefix}"
    assert_success $?
    if [ -f ${req_file} ] ; then
	${prefix}/bin/pip install -r ${req_file} \
		 --no-build-isolation --no-cache-dir
    fi
    assert_success $?
}

# entryi point
function main() {
    prefix=$1 ; shift
    if [ "$prefix" == "--help" ] ; then
       printf "${USAGE}"
       exit 0
    elif [ -z "$prefix" ] ; then
	prefix="env"
    fi
    echo "installing environment to ${prefix}..."
    install $prefix
}

main $@
