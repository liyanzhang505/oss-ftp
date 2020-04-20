# -*- coding: utf-8 -*-

import os, sys
import platform

current_path = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.abspath(os.path.join(current_path, os.pardir))
if root_path not in sys.path:
    sys.path.append(root_path)

if sys.platform.startswith("linux"):
    python_lib_path = None
    if (platform.architecture()[0] == '32bit'):
        python_lib_path = os.path.abspath( os.path.join(root_path, "python27", "unix", "lib32"))
    else:
        python_lib_path = os.path.abspath( os.path.join(root_path, "python27", "unix", "lib64"))
    sys.path.append(python_lib_path)
elif sys.platform == "darwin":
    python_lib_path = os.path.abspath( os.path.join(root_path, "python27", "macos", "lib"))
    sys.path.append(python_lib_path)
    extra_lib = "/System/Library/Frameworks/Python.framework/Versions/2.7/Extras/lib/python/PyObjc"
    sys.path.append(extra_lib)
elif sys.platform == "win32":
    pass
else:
    raise RuntimeError("detect platform fail:%s" % sys.platform)

import defaults
import logging
from logging.handlers import RotatingFileHandler
import errno
from optparse import OptionParser
import re

from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from ftp_authorizer import FtpAuthorizer
from oss_fs import OssFS

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def set_logger(level):
    #log related
    work_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    log_dir = work_dir + '/data/ossftp/'
    mkdir_p(log_dir)
    LOGFILE = log_dir + "ossftp.log"
    MAXLOGSIZE = 10*1024*1024 #Bytes
    BACKUPCOUNT = 30
    FORMAT = \
        "%(asctime)s %(levelname)-8s[%(filename)s:%(lineno)d(%(funcName)s)] %(message)s"
    handler = RotatingFileHandler(LOGFILE,
                mode='w',
                maxBytes=MAXLOGSIZE,
                backupCount=BACKUPCOUNT)
    formatter = logging.Formatter(FORMAT)
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(handler)

# Before the ftp server running, used debug level, and after running use a new level.
set_logger("DEBUG")
_logger = logging.getLogger(__name__)



def parse_ports_range(ports_str):
    m = re.match(r'^\d+~\d+$', ports_str)
    if m is None:
        _logger.error("passive_ports parse error, it should be like --passive_ports=51000~52000")
        exit(1)

    try:
        ports_str_list = ports_str.split("~")
        left = int(ports_str_list[0])
        right = int(ports_str_list[1])
        assert left < right
        return range(left, right)
    except Exception as e:
        _logger.error("passive_ports parse error, it should be like --passive_ports=51000~52000")
        exit(1)


def start_ftp(masquerade_address, listen_address, port, log_level, bucket_endpoints, internal, passive_ports_str=None, buff_size=5, protocol='https'):

    if log_level == "DEBUG":
        level = logging.DEBUG
    elif log_level == "INFO":
        level = logging.INFO
    elif log_level == "WARNING":
        level = logging.WARNING
    elif log_level == "ERROR":
        level = logging.ERROR
    elif log_level == "CRITICAL":
        level = logging.CRITICAL
    else:
        _logger.error("wrong loglevel parameter: %s" % log_level)
        exit(1)

    defaults.set_oss_trans_protocol(protocol)
    defaults.set_data_buff_size(buff_size * 1024 * 1024)
    _logger.debug('set oss transport protocol: %s' % defaults.get_oss_trans_protocol())
    _logger.debug('set buff_size: %d Byte.' % defaults.get_data_buff_size())

    passive_ports = parse_ports_range(passive_ports_str)

    authorizer = FtpAuthorizer()
    if bucket_endpoints != "":
        for url in bucket_endpoints.strip().split(','):
            if len(url.split('.', 1)) != 2:
                _logger.error("url:%s format error." % url)
                continue
            bucket_name, endpoint = url.split('.', 1)
            authorizer.bucket_endpoints[bucket_name] = endpoint
    authorizer.internal = internal
    handler = FTPHandler
    handler.permit_foreign_addresses = True
    if handler.masquerade_address != "":
        handler.masquerade_address = masquerade_address 
    handler.authorizer = authorizer
    handler.abstracted_fs = OssFS
    handler.banner = 'oss ftpd ready.'
    handler.masquerade_address = listen_address
    handler.passive_ports = passive_ports
    address = (listen_address, port)
    set_logger(level)
    server = FTPServer(address, handler)
    server.serve_forever()


def main(args, opts):
    listen_address = "127.0.0.1"
    masquerade_address = listen_address
    port = 2048 
    log_level = "DEBUG"
    bucket_endpoints = ""
    internal = None
    passive_ports_str = '51000~52000'
    buff_size = 5
    protocol = 'https'

    if opts.protocol in ['http', 'https']:
        protocol = opts.protocol
    if opts.passive_ports:
        passive_ports_str = opts.passive_ports
    if opts.buff_size:
        buff_size = int(opts.buff_size)
    if opts.masquerade_address:
        masquerade_address = opts.masquerade_address
    if opts.listen_address:
        listen_address = opts.listen_address
    if opts.port:
        try:
            port = int(opts.port)
        except ValueError:
            _logger.error("invalid FTP port, please input a valid port like --port=2048")
            exit(1)

    if opts.loglevel:
        log_level = opts.loglevel
    
    if opts.bucket_endpoints:
        bucket_endpoints = opts.bucket_endpoints

    if opts.internal:
        internal = opts.internal
    start_ftp(masquerade_address, listen_address, port, log_level, bucket_endpoints, internal, passive_ports_str, buff_size, protocol)
    
if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("", "--masquerade_address", dest="masquerade_address", help="the ip that will reply to FTP Client, then client will send data request to this address.")
    parser.add_option("", "--listen_address", dest="listen_address", help="the address which ftpserver will listen, default is 127.0.0.1")
    parser.add_option("", "--port", dest="port", type='int', help="the local port which ftpserver will listen, default is 2048")
    parser.add_option("", "--passive_ports", dest="passive_ports", help="the passive ports range which ftpserver should be opened, default is 51000~52000")
    parser.add_option("", "--buff_size", dest="buff_size", type='int', help="the buff size is used for send data, default is 5, unit is MB.")
    parser.add_option("", "--loglevel", dest="loglevel", help="DEBUG/INFO/")
    parser.add_option("", "--bucket_endpoints", dest="bucket_endpoints", help="use this endpoint to access oss")
    parser.add_option("", "--internal", dest="internal", help="access oss from internal domain or not")
    parser.add_option("", "--protocol", dest="protocol", default='https', help="https/http, default is https.")
    (opts, args) = parser.parse_args()
    main(args, opts)
