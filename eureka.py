#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2020, lijunya <445450639@qq.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import json
import urllib2

from ansible.module_utils.basic import *

DOCUMENTATION = """
---
module: eureka
short_description: Manage your micro service on Eureka
"""

EXAMPLES = """
---
- name: without instanceID get all instance info or get specific instance info
  eureka:
    url: "http://1.2.3.4:1111"
    appID: "outer"
    instanceID: "1234"
  register: result

- name: the instance info register in info
  debug: msg={{ result.info }}

- name: offline service
  eureka:
    url:  "http://1.2.3.4:1111"
    appID: "abc"
    instanceID: "1234" #下线指定的instance.
    state: offline
    force: False  #如果instanceID和host都未指定, force值为True强制下线所有实例. 为false则不允许下线所有服务,返回fail
    host: '192.168.1.4' #当instanceID未设定时. 下线该运行在该服务器上的实例
  register: result
"""

import traceback
import logging
import logging.handlers
import os
from logging.handlers import TimedRotatingFileHandler
import sys


# LOG_FILENAME = "jianguo.log"

# logging.basicConfig(filename=LOG_FILENAME, level=logging.DEBUG)

# logger = logging.getLogger("my_logger")
# logger.setLevel(logging.DEBUG)

# handler = logging.handlers.RotatingFileHandler(
#     filename=LOG_FILENAME,
#     maxBytes=1024 * 1024 * 50,  # 日志大小： 50M
#     backupCount=5,  # 备份次数： 5次
# )

# logger.addHandler(handler)
# logger.debug("hello")


class CustomLog:
    def __init__(self, name, log_dir, log_filename):
        self.name = name
        self.log_dir = log_dir
        self.log_filename = log_filename

    def get_logger(self):
        return logging.getLogger(self.name)

    def get_formatter(self, name="verbose"):
        if name == "verbose":
            return logging.Formatter(
                "%(asctime)s - %(levelname)s - %(filename)s[line:%(lineno)d] - %(funcName)s - %(message)s"
            )
        # 这里可以自定义其他formtter

    def get_handler(self, handler="timed"):
        filename = os.path.join(self.log_dir, self.log_filename)
        if handler == "timed":
            return TimedRotatingFileHandler(
                filename=filename,  # 文件名
                when="D",  # 按天切分
                backupCount=10,  # 备份分数
                encoding="utf8",  # 编码
            )
        else:
            return logging.handlers.RotatingFileHandler(
                filename=filename,
                maxBytes=1024 * 1024 * 50,  # 日志大小： 50M
                backupCount=5,  # 备份次数： 5次
            )

    def config_logger(self):
        logger = self.get_logger()

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)

        formatter = self.get_formatter("verbose")
        file_handler = self.get_handler("rotate")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)  # 记录自定义的日志

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.DEBUG)
        logger.addHandler(stream_handler)
        logger.setLevel(logging.INFO)
        return logger


logger = CustomLog(
    name="logger",
    log_dir="/tmp",
    log_filename="eureka.log",
)
logger = logger.config_logger()


def my_request(url, method="GET"):
    try:
        headers = {"Accept": "application/json"}
        request = urllib2.Request(url, headers=headers)
        logger.info(url, headers)
        request.get_method = lambda: method.upper()
        response = urllib2.urlopen(request, timeout=5)
        text = response.read()
        logger.info(text)
        return {"code": response.code, "text": text }
    except urllib2.URLError, e:
        logger.info(e)
        if hasattr(e, "code"):
            return {"code": e.code, "text": e.read()}
        elif hasattr(e, "reason"):
            return {"code": 500, "text": e.reason}
        else:
            return {"code": 500}


# 获取eureka服务信息, 传入服务实例名称获取或者传入ip地址获取该地址对应的实例信息
# 只支持单ip, 一台主机只能有一个同名服务
# 如果实例id和主机名都没传, 返回该应用下所有服务
def get_status(params):
    ret = my_request(params["status_url"])
    logger.info(ret)
    if ret["code"] == 404:
        #如果已全部下线或者是单台服务挂了.找不到该服务
        return {"status": 404}
    if ret["code"] != 200:
        return False
    ret = json.loads(ret["text"])
    info = {}
    if params["instanceID"]:
        ret = ret["instance"]
        info = {
            "appID": ret["app"],
            "instanceID": ret["instanceId"],
            "ipAddr": ret["ipAddr"],
            "status": ret["status"],
            "port": ret["port"]["$"],
            "healthCheckUrl": ret["healthCheckUrl"],
        }
    elif params["host"] is not None:
        for instance in ret["application"]["instance"]:
            if instance["ipAddr"] == params["host"]:
                info = {
                    "appID": instance["app"],
                    "instanceID": instance["instanceId"],
                    "ipAddr": instance["ipAddr"],
                    "status": instance["status"],
                    "port": instance["port"]["$"],
                    "healthCheckUrl": instance["healthCheckUrl"],
                }
        if not info:
            return {"status": 404}
    else:
        info = []
        for instance in ret["application"]["instance"]:
            info.append(
                {
                    "appID": instance["app"],
                    "instanceID": instance["instanceId"],
                    "ipAddr": instance["ipAddr"],
                    "status": instance["status"],
                    "port": instance["port"]["$"],
                    "healthCheckUrl": instance["healthCheckUrl"],
                }
            )
    #print("get_status:%s" %info)
    return info


def offline_service(params):
    info = get_status(params)
    if not info:
        return False
    if isinstance(info, list):
        # 是否强制下线整个服务
        if params["force"]:
            services = info
            for info in services:
                url = params[
                    "url"
                ] + "/eureka/apps/%s/%s/status?value=OUT_OF_SERVICE" % (
                    info["appID"],
                    info["instanceID"],
                )
                ret = my_request(url, "PUT")
            if ret["code"] == 200:
                return True
            else:
                return False
        else:
            return False
    elif info["status"] == 404:
        return True
    else:
        # 覆盖状态,强制下线. 防止心跳重新注册上服务
        url = params["url"] + "/eureka/apps/%s/%s/status?value=OUT_OF_SERVICE" % (
            info["appID"],
            info["instanceID"],
        )
        ret = my_request(url, "PUT")
        if ret["code"] == 200:
            return True
        else:
            return False


def online_service(params):
    info = get_status(params)
    if not info:
        return False
    # 删除覆盖状态
    if isinstance(info, list):
        services = info
        for info in services:
            url = params["url"] + "/eureka/apps/%s/%s/status?value=UP" % (
                info["appID"],
                info["instanceID"],
            )
            ret = my_request(url, "DELETE")
        if ret["code"] == 200:
            return True
        else:
            return False
    elif info["status"] == 404:
        return False
    else:
        url = params["url"] + "/eureka/apps/%s/%s/status?value=UP" % (
            info["appID"],
            info["instanceID"],
        )
        ret = my_request(url, "DELETE")
        if ret["code"] == 200:
            return True
        else:
            return False


def delete_service(params):
    info = get_status(params)
    if not info:
        return False
    if isinstance(info, list):
        # 是否强制下线整个服务
        if params["force"]:
            services = info
            for info in services:
                url = params["url"] + "/eureka/apps/%s/%s" % (
                    info["appID"],
                    info["instanceID"],
                )
                ret = my_request(url, "DELETE")
            if ret["code"] == 200:
                return True
            else:
                return False
        else:
            return False
    elif info['status'] == 404:
        return True
    else:
        # 覆盖状态,强制下线. 防止心跳重新注册上服务
        url = params["url"] + "/eureka/apps/%s/%s" % (info["appID"], info["instanceID"])
        ret = my_request(url, "DELETE")
        if ret["code"] == 200:
            return True
        else:
            return False


def healthCheck(params):
    if params['healthCheckUrl']:
        url = params["healthCheckUrl"]
    else:
        info = get_status(params)
        logger.info(info)
        if not info or info["status"] == 404:
            return False
        url = info["healthCheckUrl"]
    ret = my_request(url)
    if ret["code"] == 200:
        try:
            checkstatus = json.loads(ret["text"])
            if checkstatus["status"] == "UP" or checkstatus["status"] == "OUT_OF_SERVICE":
                return True
        except:
            pass
    if ret["code"] == 503:
        try:
            checkstatus = json.loads(ret["text"])
            if checkstatus["status"] == "OUT_OF_SERVICE":
                return True
        except:
            pass
    if "actuator/" in url:
        url = url.replace("actuator/", "")
        ret = my_request(url)
        if ret["code"] == 200:
            try:
                checkstatus = json.loads(ret["text"])
                if checkstatus["status"] == "UP" or checkstatus["status"] == "OUT_OF_SERVICE":
                    return True
            except:
                pass
        if ret["code"] == 503:
            try:
                checkstatus = json.loads(ret["text"])
                if checkstatus["status"] == "OUT_OF_SERVICE":
                    return True
            except:
                pass
    return False


def check_service_up(params):
    info = get_status(params)
    if not info:
        return False
    if isinstance(info, list):
        services = info
        for info in services:
            if info["status"] != "UP":
                return False
    else:
        if info["status"] != "UP":
            return False
    return True


def main():
    fields = {
        "url": {"required": True, "type": "str"},
        "appID": {"required": True, "type": "str"},
        "instanceID": {"required": False, "default": "", "type": "str"},
        "force": {"required": False, "default": False, "type": "bool"},
        "host": {"required": False, "type": "str"},
        "healthCheckUrl": {"required": False, "type": "str"},
        "state": {"choices": ["offline", "online", "delete", "checkup", "healthCheck"], "type": "str"},
    }

    choice_map = {
        "offline": offline_service,
        "online": online_service,
        "delete": delete_service,
        "checkup": check_service_up,
        "healthCheck": healthCheck,
    }

    module = AnsibleModule(argument_spec=fields)
    if module.params["url"].startswith("http://"):
        module.params["url"] = module.params["url"].strip("/")
    else:
        module.params["url"] = "http://" + module.params["url"].strip("/")
    url = module.params["url"].strip()
    appID = module.params["appID"].strip()
    instanceID = module.params["instanceID"].strip()

    module.params["status_url"] = url + "/eureka/apps/%s/%s" % (appID, instanceID)

    if module.params["state"] is not None:
        ret = choice_map.get(module.params["state"])(module.params)
        logger.info("health check return:" + str(ret))
        if ret:
            if module.params["state"] == "checkup" or module.params["state"] == "healthCheck":
                module.exit_json(ok=True)
            else:
                module.exit_json(changed=True)
        else:
            module.fail_json(ok=False, msg="%s failed" % (module.params["state"]))
    else:
        ret = get_status(module.params)
        if not ret:
            module.fail_json(msg="Get Eureka Info Failed")
        else:
            module.exit_json(ok=True, info=ret)


if __name__ == "__main__":
    main()
