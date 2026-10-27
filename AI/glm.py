''' 
glm 模型调用模块
'''
from typing import List, Optional
# 从typing 模块导入了两个 类型提示工具 ：
# List 表示列表类型，表示一个列表，`List[dict]` 即“元素为 dict 的列表”
# Optional 表示可选类型 `Optional[str]` 等价于`Union[str, None]` ，即“可能是字符串，也可能是 None”

import requests

from Backend.config import GLM_API_KEY, GLM_MODEL, GLM_TIMEOUT_SECONDS, GLM_URL
# 调用glm模型
def chat(messages: List[dict], model: Optional[str] = None) -> Optional[str]:
    # `List[dict]` ：声明`messages` 参数是一个消息列表（每条是`{"role": ..., "content": ...}` 的字典）
    # `Optional[str]` 有两处语义：
    # 1. 入参 ：`model: Optional[str] = None` 
    # 表示调用方可以不指定模型（用 config 默认槽位），也可以显式传入某个模型名（供候选池滚动测试逐个指定）
    # 返回值 ：`-> Optional[str]` 明确告诉调用方——这个函数 可能返回 None 。
    # 这非常关键，因为这个函数设计了多重失败路径（未配置 Key、接口异常、网络错误都返回`None` ），
    # 返回值注解强制提醒调用方必须做空值判断，配合你们项目的“三级降级链路”（主模型→备用模型→演示模式），
    # 上层路由正是靠检查`None` 来决定切换下一个模型的。

    # model 参数供候选池滚动测试逐个指定模型，不传则用 config 默认槽位
    if not GLM_API_KEY:
        return None  # 未配置Key → 跳过，由路由尝试另一个模型
    try:
        # 调用glm模型
        # 发送POST请求到glm接口，包含模型、消息、温度等参数
        # 超时时间设置为GLM_TIMEOUT_SECONDS秒

        # 四个参数的作用
        # ### 1. GLM_URL — 请求目标
        # 向向智谱开放平台的 API 端点发送 POST 请求（形如`https://open.bigmodel.cn/api/paas/v4/chat/completions` ）。
        # URL 定义在 config.py /Trae_project/Anda/Backend/config.py 中，
        # 遵循项目“AI模型配置通过 .env 按能力槽位定义”的约定。
        # ### 2. headers — 请求头
        # - `Content-Type: application/json` ：告诉服务器请求体是 JSON 格式
        # - `Authorization: Bearer {GLM_API_KEY}` ：通过获取的api key进行身份鉴权。
        # 这是 HTTP 标准的 Bearer Token 方案
        # `f"Bearer {GLM_API_KEY}"` 用 f-string 把 Key 拼进协议要求的前缀里。
        # API Key 只从`.env` 环境变量读取进入内存，不硬编码在代码里，1.符合安全规范 2.避免在上传代码到public仓库时暴露敏感信息
        # ### 3. json={...} — 请求体（模型API的核心三要素）
        # 注意这里用的是`json=` 而不是`data=` ，`requests` 库会自动把字典序列化为 JSON 字符串并设置好 Content-Type：
        # 字段 作用 `"model": model or GLM_MODEL` 指定模型名 。
        # 这里用了 Python 的`or` 短路技巧：`model` 参数非空（候选池滚动测试显式指定）就用它，否则回退到 config 默认槽位模型。
        # 等价于“传了就覆盖，没传就用默认” `"messages": messages` 对话内容 。
        # 就是 prompt.py /Trae_project/Anda/AI/prompt/prompt.py) 
        # 的`build_messages()` 拼出来的`[system, 历史轮次..., user问题]` 数组，
        # 两个模块在此完成对接 `"temperature": 0.7` 随机度/创造性 。取值 0~1（智谱范围），
        # 越低回答越确定刻板，越高越发散有创意。0.7 是聊天场景的常见折中值
        # ### 4. timeout=GLM_TIMEOUT_SECONDS — 超时保护
        # 这是这段代码里最容易被忽视但最关键的一行 。
        # 如果省略`timeout` ，`requests` 会无限期等待 
        # 模型服务一旦卡死，后端工作线程就会被永久挂起，整个降级链路（主模型→备用模型→演示模式）全部失效。
        # 设置超时后，超时会抛出异常，被下方`except` 捕获返回`None` ，上层路由就能立即切换到下一个备用模型。
        resp = requests.post(  
            GLM_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {GLM_API_KEY}"},
            json={"model": model or GLM_MODEL, "messages": messages, "temperature": 0.7},
            timeout=GLM_TIMEOUT_SECONDS,
        )
        # 在此时 requests.post 开始连接云端服务器 完成一次完整的 HTTP 通讯 
        # DNS 解析 TCP 握手 TLS 握手 发送请求：把 headers（鉴权）+ json 请求体（messages）打包成 HTTP 报文发出 
        # 阻塞等待 等待服务器响应 收到响应 ：服务器把回复 JSON 发回来，`resp` 对象才被赋值

        # 解析JSON响应  注意是本地！ 完整躺在内存里的`resp` 对象中
        # 从响应体中提取模型回复（`choices[0].message.content`）
        data = resp.json()
        # 转换成字典格式便于取值
        # `requests` 拿到响应后，`resp` 对象里的原始内容只是 JSON 格式的 字符串字节流 ，
        # `resp.json()` 负责把它反序列化成 Python 字典。这一步发生在 本地内存 中，不再有网络开销。成功时`data` 长这样：
        # JSON 格式
        # {
        #   "choices": [
        #     {"message": {"role": "assistant", "content": "模型回复的文本"}, "finish_reason": "stop"}
        #   ],
        #   "usage": {"prompt_tokens": 100, "completion_tokens": 50}
        # }
        if "choices" not in data:
            # ### 2. if "choices" not in data: — 失败拦截（防御性核心）
            # 这一行是整个函数 最重要的防御逻辑 。
            # 背景是：智谱 API 出错时（Key 无效、余额不足、模型名写错、触发限流）， 
            # 不会返回 4xx/5xx 状态码抛异常，而是返回 HTTP 200 + 错误 JSON ：
            # JSON 格式
            # `{"error": {"code": "1002", "message": "Authorization Token 非法"}}`
            # 如果直接写`data["choices"]` ，Python 会抛`KeyError` ，
            # 而且这个 KeyError 会被下方`except Exception` 捕获——你只能看到一句干巴巴的`'choices'` ， 
            # 真正的失败原因（“Token 非法”）被完全吞掉 ，排查问题时会一头雾水。
            # 所以这里用`"choices" not in data` 显式判断，
            # 失败时打印 完整的错误结构 （包含 status_code 和 error 详情），再返回`None` 交给上层降级链路。
            # 注释里的“否则真实原因会被KeyError吞掉”说的就是这个坑。
            # 智谱报错时不抛HTTP异常而是返回error结构，这里显式拦截，否则真实原因会被KeyError吞掉
            if resp.status_code == 429:
                # 免费模型高峰期限流，属正常现象：路由会自动切备用模型，体检到期自动恢复
                print(f"[glm] {model or GLM_MODEL} 限流中 (HTTP 429 高峰期访问量大)，已自动切备用模型")
            else:
                print(f"[glm] 接口异常 o-o !!! (HTTP {resp.status_code}): {data}")
                # 将错误原因打印到控制台上，方便调试
            return None
            # 返回 None 表示调用失败，上层路由会切换到下一个模型或演示模式
        # 成功时返回模型回复
        return data["choices"][0]["message"]["content"]
        # ### 3. return data["choices"][0]["message"]["content"] — 成功路径
        # 三层字典取值，按 OpenAI 兼容格式逐层下钻：
        # 层级 含义 `data["choices"]` 候选回复数组（本次请求可能有多个候选，默认只生成 1 个）
        # `[0]` 取第一个候选回复 `["message"]["content"]` 回复消息体中的 纯文本内容 ——就是最终要返回给用户的那句话
        # `finish_reason` 、`usage` （token 用量）等字段这里没用到，直接丢弃了。
        # 如果以后想做 token 统计或成本核算，可以在这附近扩展。
    except Exception as exc:
        print(f"[glm] 调用失败了哦~  ?-? : {exc}")
        return None
        # ### 4. except Exception as exc: — 网络层兜底
        # 这个 catch 拦截的是 请求阶段 抛出的所有异常，典型的有：
        # - `requests.exceptions.Timeout` — 超过了`GLM_TIMEOUT_SECONDS` 
        # （这就是超时保护的落点，异常被吃掉后返回`None` ，上层立即切备用模型，线程不会被卡死）
        # - `requests.exceptions.ConnectionError` — DNS 解析失败、网络不通  
        # - `json.JSONDecodeError` — 服务器返回了非 JSON 内容（如网关错误页）