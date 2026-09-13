"""Trusted root directory setup that never follows workspace symlinks."""
import os
import pwd
import subprocess


def ensure_directory(path, owner=0, mode=0o755):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.strip('/').split('/'):
            try: os.mkdir(part,dir_fd=fd)
            except FileExistsError: pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        os.fchown(fd,owner,owner);os.fchmod(fd,mode)
    finally:os.close(fd)


def initialize():
    try: pwd.getpwnam('sandbox')
    except KeyError: subprocess.run(['useradd','-m','-o','-u','1000','-s','/bin/bash','sandbox'],check=True)
    for path in ['/opt/lab','/opt/lab/bin']:
        ensure_directory(path)
    for path in ['/var/lib/lab','/var/lib/lab/requests']:
        ensure_directory(path,mode=0o700)
    for path in ['/home/sandbox','/home/sandbox/.cache','/home/sandbox/.cache/lab-npm','/home/sandbox/project','/home/sandbox/project/artifacts','/workspace']:
        ensure_directory(path,owner=1000)


if __name__=='__main__':initialize()
