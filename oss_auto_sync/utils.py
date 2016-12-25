# -*- coding: utf-8 -*-

"""
utils
"""
from hashlib import md5
import requests
import time
import os.path as path


def get_server_time():
    """
    get server time (GMT timestamp)
    :return:
    """
    response = requests.get('http://www.aliyun.com')
    t = response.headers.get('date')
    time_tuple = time.strptime(t[5:25], "%d %b %Y %H:%M:%S")
    stamp = int(time.mktime(time_tuple))
    return stamp


def file_md5(file_path):
    """
    calculation file md5 (upper case)
    :param file_path:
    :return:
    """
    if path.isdir(file_path):
        raise TypeError('input is a directory, use "dir_md5()" instead')
    m = md5()
    a_file = open(file_path, 'rb')  # 需要使用二进制格式读取文件内容
    m.update(a_file.read())
    a_file.close()
    return m.hexdigest().upper()


def dir_md5(dir_path):
    """
    calculate directory md5 (upper case)
    :param dir_path:
    :return:
    """
    pass


def remote_normpath(remote_path):
    """
    normalize remote path
    e.g. foo/bar/ --directory
    e.g. foo/bar/foobar.txt --file
    :param remote_path:
    :return:
    """
    isdir = False
    if remote_path.endswith(('\\', '/')):
        isdir = True
    remote_path = path.normpath(remote_path).replace('\\', '/')
    if isdir:
        remote_path += '/'
    return remote_path
