# Copyright (c) 2012-2014 The CEF Python authors. All rights reserved.
# License: New BSD License.
# Website: http://code.google.com/p/cefpython/

# Create a setup package.

import sys
import os
import platform
import argparse
import re
import platform
import shutil
import glob
import sysconfig
import subprocess

BITS = platform.architecture()[0]
assert (BITS == "32bit" or BITS == "64bit")
if BITS == "32bit":
    LINUX_BITS = "linux32"
else:
    LINUX_BITS = "linux64"
PACKAGE_NAME = "cefpython3"

README_FILE = os.getcwd()+r"/README.txt"
INIT_TEMPLATE = os.getcwd()+r"/__init__.py.template"
SETUP_TEMPLATE = os.getcwd()+r"/setup.py.template"
SETUP_CFG_TEMPLATE = os.getcwd()+r"/setup.cfg.template"

def str_format(string, dictionary):
    orig_string = string
    for key, value in dictionary.iteritems():
        string = string.replace("%("+key+")s", value)
    if string == orig_string:
        raise Exception("Nothing to format")
    if re.search(r"%\([a-zA-Z0-9_]+\)s", string):
        raise Exception("Not all strings formatted")
    return string

def main():
    parser = argparse.ArgumentParser(usage="%(prog)s [options]")
    parser.add_argument("-v", "--version", help="cefpython version",
            required=True)
    args = parser.parse_args()
    assert re.search(r"^\d+\.\d+$", args.version), (
            "Invalid version string")

    vars = {}
    vars["APP_VERSION"] = args.version
    vars["PLATFORM"] = sysconfig.get_platform()
    vars["PY_VERSION_DIGITS_ONLY"] = (str(sys.version_info.major) + ""
            + str(sys.version_info.minor)) # "27" or "34"

    print("Reading template: %s" % README_FILE)
    f = open(README_FILE)
    README_CONTENT = f.read()
    f.close()

    print("Reading template: %s" % INIT_TEMPLATE)
    f = open(INIT_TEMPLATE)
    INIT_CONTENT = str_format(f.read(), vars)
    f.close()

    print("Reading template: %s" % SETUP_TEMPLATE)
    f = open(SETUP_TEMPLATE)
    SETUP_CONTENT = str_format(f.read(), vars)
    f.close()

    print("Reading template: %s" % SETUP_CFG_TEMPLATE)
    f = open(SETUP_CFG_TEMPLATE)
    SETUP_CFG_CONTENT = str_format(f.read(), vars)
    f.close()

    installer_dir = os.path.dirname(os.path.abspath(__file__))

    setup_dir = installer_dir+"/"+PACKAGE_NAME+"-"+vars["APP_VERSION"]+"-"+LINUX_BITS+"-setup"
    print("Creating setup dir: "+setup_dir)
    os.mkdir(setup_dir)

    package_dir = setup_dir+"/"+PACKAGE_NAME
    print("Creating package dir")
    os.mkdir(package_dir)

    print("Copying License file")
    shutil.copy("../../../License", package_dir)


    print("Creating README.txt from template")
    with open(setup_dir+"/README.txt", "w") as f:
        f.write(README_CONTENT)

    print("Creating setup.py from template")
    with open(setup_dir+"/setup.py", "w") as f:
        f.write(SETUP_CONTENT)

    print("Creating setup.cfg from template")
    with open(setup_dir+"/setup.cfg", "w") as f:
        f.write(SETUP_CFG_CONTENT)

    binaries_dir = os.path.abspath(installer_dir+"/../binaries_"+BITS+"/")
    print("Copying binaries to package dir")
    ret = os.system("cp -rf "+binaries_dir+"/* "+package_dir)
    assert ret == 0

    os.chdir(package_dir)
    print("Removing .log files from the package dir")
    ret = os.system("rm *.log")
    # assert ret == 0 - if there are no .log files this assert would fail.
    os.chdir(installer_dir)

    print("Creating __init__.py from template")
    with open(package_dir+"/__init__.py", "w") as f:
        f.write(INIT_CONTENT)

    print("Creating examples dir in package dir")
    os.mkdir(package_dir+"/examples/")

    print("Moving kivy-select-boxes dir to examples dir")
    shutil.move(package_dir+"/kivy-select-boxes",
            package_dir+"/examples/kivy-select-boxes")

    print("Creating wx dir in package dir")
    os.mkdir(package_dir+"/wx/")

    print("Moving example scripts from package dir to examples dir")
    examples = glob.glob(package_dir+"/*.py")
    for example in examples:
        # Ignore: cefpython_py27.py - dummy API script
        if os.path.basename(example).startswith("cefpython_"):
            continue
        # Ignore: __init__.py
        if os.path.basename(example).startswith("__"):
            continue
        os.rename(example, package_dir+"/examples/"+os.path.basename(example))
    ret = os.system("mv "+package_dir+"/*.html "+package_dir+"/examples/")
    ret = os.system("mv "+package_dir+"/*.js "+package_dir+"/examples/")
    ret = os.system("mv "+package_dir+"/*.css "+package_dir+"/examples/")
    assert ret == 0

    print("Copying wx/ to package dir")
    wx_subpackage_dir = os.path.abspath(installer_dir+"/../../wx/")
    ret = os.system("cp -rf "+wx_subpackage_dir+"/* "+package_dir+"/wx/")
    assert ret == 0

    print("Moving wx examples from wx/examples to examples/wx")
    shutil.move(package_dir+"/wx/examples", package_dir+"/wx/wx/")
    shutil.move(package_dir+"/wx/wx/", package_dir+"/examples/")

    print("Copying package dir examples to setup dir")
    ret = os.system("cp -rf "+package_dir+"/examples/ "+setup_dir+"/examples/")
    assert ret == 0

    # Create empty debug.log files so that package uninstalls cleanly
    # in case examples were launched. Issue 149.
    debug_log_dirs = [package_dir, 
                      package_dir+"/examples/", 
                      package_dir+"/examples/wx/"]
    for dir in debug_log_dirs:
        print("Creating empty debug.log in %s" % dir)    
        with open(dir+"/debug.log", "w") as f:
            f.write("")
        # Set write permissions so that Wheel package files have it
        # right. So that examples may be run from package directory.
        subprocess.call("chmod 666 %s/debug.log" % dir, shell=True)

    print("Setup Package created successfully.")

if __name__ == "__main__":
    main()
