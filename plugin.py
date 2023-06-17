import base64
import io
import json
import os.path
import re

import requests

import plugins
from bridge.bridge import Bridge
from bridge.context import *
from bridge.reply import ReplyType, Reply
from common import const
from common.expired_dict import ExpiredDict
from common.log import logger
from plugins import *
from config import conf


class Mj():
    def __init__(self, base_url, module):
        self.base_url = base_url
        self.pre_prompt = ""
        self.status = ""  # drawing 使用id 查询， using 使用 useid 查询； done => 绘制完成，可以进入 using 或者 v 状态,
        self.process = 0
        self.img = None
        self.id = None
        self.useid = None
        self.module = module
        self.status = ""
        self.pic_b64 = ""

    def draw(self, context: Context):
        if self.status == "drawing" or self.status == "using":
            respone = self.method_respone("FETCH")
            if respone.json()['status'] == 'FAILURE':
                reply = Reply(ReplyType.ERROR, "生成失败，请重试。失败原因：" + respone.json()['failReason'])
            elif respone.json()['status'] == 'SUCCESS':
                res_img = requests.get(respone.json()['imageUrl']).content
                self.img = io.BytesIO(res_img)
                reply = Reply(ReplyType.IMAGE, self.img)
                self.status = "done"
            elif respone.json()['status'] == 'IN_PROGRESS':
                reply = Reply(ReplyType.INFO, f"图像正在生成目前进度为{respone.json()['progress']}，请稍等一下")
                return reply
            elif respone.json()['status'] == 'SUBMITTED':
                if respone.json()["action"] == "IMAGINE":
                    reply = Reply(ReplyType.INFO,
                                  f"任务处于SUBMITTED, 可能触发人工验证, id:{self.id}, 建议 mj start 重置 或者 mj stop 退出绘画")
                else:
                    reply = Reply(ReplyType.INFO,
                                  f"任务处理中，进度为{respone.json()['progress']}, 请稍等一下")
                return reply
            else:
                reply = Reply(ReplyType.ERROR, f"未知错误 , resp:{respone.json()}")
            return reply
        elif self.status == "done":
            cmd = context.content
            regex = r"(?P<act>[U,u,v,V])(?P<num>\d)"
            res = re.search(regex, cmd)
            if res:
                act = res.group("act")
                num = res.group("num")
                if act.upper() == "U":
                    data_body = {**self.module.get("UPSCALE")["body"],
                                 **{"taskId": self.id, "index": int(num)}}
                    response = self.method_respone("UPSCALE", **data_body)
                    if response.status_code == 200:
                        self.useid = response.json()["result"]
                        self.status = "using"
                        reply = Reply(ReplyType.INFO, f"使用图片指令发送成功,稍后回复任意消息接收第{num}张图")
                        return reply
                elif act.upper() == "V":
                    data_body = {**self.module.get("VARIATION")["body"],
                                 **{"taskId": self.id, "index": int(num)}}
                    response = self.method_respone("VARIATION", **data_body)
                    if response.status_code == 200:
                        self.id = response.json()["result"]
                        self.status = "drawing"
                        reply = Reply(ReplyType.INFO, f"图片变换指令发送成功,稍后回复任意消息查看扩展结果")
                        return reply
                else:
                    reply = Reply(ReplyType.INFO,
                                  f"你可以使用U1,U2,U3,U4确认使用的图片，或者V1,V2,V3,V4 变换指定序号的图片")
                    return reply
            else:
                reply = Reply(ReplyType.INFO,
                              f"你可以使用U1,U2,U3,U4确认使用的图片，或者V1,V2,V3,V4 扩展指定序号的图片, mj stop 退出绘画")
                return reply
        else:

            if context.type == ContextType.TEXT:
                logger.info("[MJ] recive text: " + context.content)
                self.pre_prompt = context.content
                if self.pic_b64 != "":
                    data_body = {**self.module.get("IMAGINE")["body"],
                                 **{"prompt": self.pre_prompt, "base64": "data:image/png;base64," + self.pic_b64}}
                else:
                    data_body = {**self.module.get("IMAGINE")["body"],
                                 **{"prompt": self.pre_prompt, "base64": ""}}
                respone = self.method_respone("IMAGINE", **data_body)
                if respone.status_code == 200:
                    if respone.json()["code"] == 1:
                        self.id = respone.json()['result']
                        reply = Reply(ReplyType.INFO,
                                      "开始生成图像！本次prompt:" + self.pre_prompt + "，本次ID：" + self.id + ",生成一般需要等待30s，请等待一段时间后回复任意消息获得结果")
                        self.status = "drawing"
                    else:
                        reply = Reply(ReplyType.ERROR,
                                      "提交失败！本次prompt:" + self.pre_prompt + "," + "desc:" + respone.json()[
                                          "description"] + "请求重新输入 prompt")
                else:
                    reply = Reply(ReplyType.ERROR, "生成失败，请重试。失败原因：" + respone.json()['failReason'])
            elif context.type == ContextType.IMAGE:
                with open(context.content, "rb") as f:
                    img = base64.b64encode(f.read()).decode()
                self.pic_b64 = img
                reply = Reply(ReplyType.INFO, "图片已接受，请求输入其他描述")
                # data_body = {**self.module.get("IMAGINE")["body"], **{"prompt": self.pre_prompt, "base64": img}}
                # respone = self.method_respone("IMAGINE", **data_body)
                # if respone.status_code == 200:
                #    self.id = respone.json()['result']
                #    reply = Reply(ReplyType.INFO,
                #                  "开始生成图像！本次prompt:" + self.pre_prompt + "，本次ID：" + self.id + ",生成一般需要等待30s，请等待一段时间后回复任意消息获得结果")
                #    self.work = True
                # else:
                #    reply = Reply(ReplyType.ERROR, "生成失败，请重试。失败原因：" + respone.json()['failReason'])
            return reply

    def method_respone(self, op_name, **kwargs):
        if op_name == "FETCH":
            id = self.id
            if self.status == "using":
                id = self.useid
            return requests.request("GET", self.base_url + self.module.get(op_name)["path"] + id + "/fetch")
        elif op_name in self.module:
            new_kwargs = {**self.module.get(op_name)["body"], **kwargs}
            return requests.request("POST", self.base_url + self.module.get(op_name)["path"], json=new_kwargs)


@plugins.register(
    name="Midjourney",
    desire_priority=0,
    desc="基于midjourney 的画图插件",
    version="0.1",
    hidden=False,
    author="nautilis",
)
class MidJourney(Plugin):
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                logger.error("[Midjourney] config.json not found!")
            else:
                logger.error("[Midjourney] init failed")
            raise e
        self.config = config
        self.commands = config.get("commands", [])
        self.trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        if conf().get("expires_in_seconds"):
            self.prompt_session = ExpiredDict(conf().get("expires_in_seconds"))
            self.instance = ExpiredDict(conf().get("expires_in_seconds"))
        else:
            self.prompt_session = dict()
            self.instance = dict()

        logger.info("[Midjourney] inited")

    def on_handle_context(self, e_context: EventContext):
        # 获取事件上下文中的内容和会话ID
        channel = e_context["channel"]
        bottype = Bridge().get_bot_type("chat")
        if bottype not in [const.OPEN_AI, const.CHATGPT, const.CHATGPTONAZURE]:
            return
        if ReplyType.IMAGE in channel.NOT_SUPPORT_REPLYTYPE:
            return
        bot = Bridge().get_bot("chat")
        context = e_context["context"]
        sessionid = context["session_id"]
        content = context.content
        content_type = context.type
        trigger_prefix = self.trigger_prefix
        if content_type == ContextType.TEXT:
            clist = content.split(maxsplit=1)
            if clist[0] == f"mj":
                if len(clist) == 1:
                    reply = self.mj_help(sessionid)
                elif clist[1] in self.commands:
                    command_handler = getattr(self, f"mj_{clist[1]}")
                    reply = command_handler(sessionid, bot)
                else:
                    reply = self.mj_help(sessionid, bot)

                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
        elif content_type == ContextType.IMAGE:
            cmsg = context["msg"]
            cmsg.prepare()
        if sessionid in self.prompt_session:
            logger.debug("[Midjourney] on handle context => {}".format(content))
            reply = self.prompt_session[sessionid].draw(context)  # todo
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

    def get_help_text(self, verbose=False, **kwargs):
        help_text = f"使用midjourney 进行画图的插件"
        return help_text

    def mj_start(self, sessionid, bot):
        if sessionid not in self.prompt_session:
            reply = Reply(ReplyType.INFO, f"开始画图！请输入文字描述, 输入{self.trigger_prefix} mj stop 停止画图。")
        else:
            reply = Reply(ReplyType.INFO, "检测到已经进入绘画模式，已重置")

        self.prompt_session[sessionid] = Mj(base_url=self.config["base_url"], module=self.config["mj_keywords"])
        return reply

    def mj_stop(self, sessionid, bot):
        if sessionid in self.prompt_session:
            del self.prompt_session[sessionid]
            reply = Reply(ReplyType.INFO, "停止画图！")
        else:
            reply = Reply(ReplyType.INFO, "当前没有正在进行中的画图！")
        return reply
