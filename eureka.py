#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2020, collin lee <445450639@qq.com>
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
    instanceID: "1234"
    state: offline
    force: False
    host: '192.168.1.4'
  register: result
"""


def my_request(url, method="GET"):
    try:
        headers = {"Accept": "application/json"}
        request = urllib2.Request(url, headers=headers)
        request.get_method = lambda: method.upper()
        response = urllib2.urlopen(request, timeout=3)
        return {"code": response.code, "text": response.read()}
    except:
        return {"code": 500}


# 获取eureka服务信息, 传入服务实例名称获取或者传入ip地址获取该地址对应的实例信息
# 只支持单ip, 一台主机只能有一个同名服务
# 如果实例id和主机名都没传, 返回该应用下所有服务
def get_status(params):
    ret = my_request(params["status_url"])
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
    else:
        # 覆盖状态,强制下线. 防止心跳重新注册上服务
        url = params["url"] + "/eureka/apps/%s/%s" % (info["appID"], info["instanceID"])
        ret = my_request(url, "DELETE")
        if ret["code"] == 200:
            return True
        else:
            return False


def check_service(params):
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
        "state": {"choices": ["offline", "online", "delete", "check"], "type": "str"},
    }

    choice_map = {
        "offline": offline_service,
        "online": online_service,
        "delete": delete_service,
        "check": check_service,
    }

    module = AnsibleModule(argument_spec=fields)
    if module.params["url"].startswith("http://"):
        module.params["url"] = module.params["url"].strip("/")
    else:
        module.params["url"] = "http://" + module.params["url"].strip("/")
    url = module.params["url"]
    appID = module.params["appID"]
    instanceID = module.params["instanceID"]

    module.params["status_url"] = url + "/eureka/apps/%s/%s" % (appID, instanceID)

    if module.params["state"] is not None:
        ret = choice_map.get(module.params["state"])(module.params)
        if ret:
            if module.params["state"] == "check":
                module.exit_json(ok=True)
            else:
                module.exit_json(changed=True)
        else:
            module.fail_json(msg="%s failed" % (module.params["state"]))
    else:
        ret = get_status(module.params)
        if not ret:
            module.fail_json(msg="Get Eureka Info Failed")
        else:
            module.exit_json(ok=True, info=ret)


if __name__ == "__main__":
    main()
