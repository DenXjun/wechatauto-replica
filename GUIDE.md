# wechatauto-replica 详细使用指南 / Detailed Usage Guide

> 面向**微信 4.x Windows 客户端**（非网页版）的自动化库。本文档覆盖从安装、
> 数据库读取、实时监听、消息发送、媒体下载、朋友圈到多账号与常见问题的
> 全部用法，并附带可直接运行的示例。
>
> Automation for the **WeChat 4.x Windows desktop client** (not the web version).
> This guide covers everything: installation, database reading, real-time
> listening, sending, media download, Moments, multi-account, and FAQ — with
> runnable examples throughout.

---

## 目录 / Table of Contents

1. [安装与准备 / Installation & Setup](#1-安装与准备--installation--setup)
2. [整体架构 / Architecture Overview](#2-整体架构--architecture-overview)
3. [数据库读取 / Database Reading (WeChatDB)](#3-数据库读取--database-reading-wechatdb)
4. [实时消息监听 / Real-time Listening](#4-实时消息监听--real-time-message-listening)
5. [发送消息 / Sending Messages](#5-发送消息--sending-messages)
6. [媒体下载 / Media Download](#6-媒体下载--media-download)
7. [朋友圈 / Moments](#7-朋友圈--moments)
8. [多账号 / Multi-account](#8-多账号--multi-account)
9. [导出聊天记录 / Export](#9-导出聊天记录--exporting-chat-history)
10. [群聊操作 / Group Chat](#10-群聊操作专题--group-chat-operations)
11. [常见问题与排错 / FAQ](#11-常见问题与排错--faq--troubleshooting)
12. [API 速查表 / Quick Reference](#12-api-速查表--api-quick-reference)

---

## 1. 安装与准备 / Installation & Setup

### 1.1 环境要求 / Requirements

| 项目 / Item | 要求 / Requirement |
|---|---|
| 系统 / OS | Windows 10 / 11 |
| Python | 3.9+（已在 3.12 验证 / verified on 3.12） |
| 微信 / WeChat | 4.1.12+（数据库读取对版本不敏感 / DB reading is version-insensitive） |
| 登录状态 / Login | 微信必须**已登录**（数据库密钥在进程内存中）/ WeChat must be **logged in** (DB keys live in process memory) |

### 1.2 安装 / Install

```bash
pip install wechatauto-replica

# 发送路径需要额外依赖（OCR 兜底 + 拼音输入）/ Sending path needs extra deps (OCR fallback + pinyin IME):
pip install winsdk pypinyin
```

从源码开发 / From source:

```bash
git clone <仓库地址 / repo>
cd wechatauto-replica
pip install -e .
```

### 1.3 验证安装 / Verify

```python
import wechatauto
print(wechatauto.__version__)   # 1.1.5.1 (beta)
```

> ⚠️ 首次运行 `WeChatDB()` 会扫描微信进程内存提取数据库密钥，首次约 6 秒，
> 之后密钥缓存到本地，秒开。
> The first `WeChatDB()` call scans the WeChat process memory to extract DB keys
> (~6s). Keys are cached locally afterwards, so later runs are instant.

---

## 2. 整体架构 / Architecture Overview

| 能力 / Capability | 技术路线 / Tech | 模块 / Module |
|---|---|---|
| **读消息 / Read** | 本地 SQLCipher 4 数据库解密 / Local SQLCipher 4 DB decryption | `db.py` (WeChatDB) |
| **实时监听 / Listen** | 数据库增量轮询 + 每会话工作线程 / DB incremental polling + per-chat workers | `db.py` (Listener) |
| **发消息 / Send** | UIA 优先，坐标 + OCR 兜底 / UIA-first, coordinate + OCR fallback | `guia.py`, `wx.py` |
| **媒体下载 / Media** | `.dat` AES 解密 / SILK 语音 / 文件复制 / `.dat` AES decrypt / SILK voice / file copy | `media.py` (MediaDownloader) |
| **朋友圈 / Moments** | `sns.db` 直读 + UIA / direct read + UIA | `moment.py` |

核心对象 / Core objects：

- `WeChatDB` —— 一切数据读取的入口（解密数据库、查消息、查联系人）/ entry point for all data reading
- `Listener` —— 实时监听器（轮询 + 工作线程）/ real-time listener
- `MediaDownloader` —— 媒体下载 / media download
- `WeChat` / `Chat` —— 面向发送的 wxauto 风格接口 / wxauto-style sending API
- `WeChatGUI` / `quick_send` —— 底层 GUI 驱动与便捷函数 / low-level GUI driver + convenience functions

---

## 3. 数据库读取 / Database Reading (WeChatDB)

### 3.1 初始化 / Init

```python
from wechatauto import WeChatDB

db = WeChatDB()          # 自动检测账号与数据目录 / auto-detect account & data dir
# db = WeChatDB(account="wxid_xxx")   # 多账号时指定 / specify account for multi-account
```

### 3.2 会话（聊天列表）/ Sessions (chat list)

```python
info = db.get_self_info()                  # 当前账号信息 / current account info
for s in db.get_sessions(limit=10):        # 会话列表 / session list
    print(s["username"], s["unread"], s["summary"])
```

`get_sessions()` 返回的 `username` 是**会话唯一标识** / unique session identifier：

- 私聊 / Private chat：`wxid_xxx`
- 群聊 / Group chat：`xxx@chatroom`

> ⚠️ 后续所有 API 都认 `username` 而非昵称。可用 `search_contact()` 转换。
> All APIs take `username`, not nickname. Use `search_contact()` to convert.

### 3.3 搜索联系人 / Search

```python
hits = db.search_contact("Ayi")            # 按昵称/备注/微信号模糊搜索 / fuzzy search
print(hits[0]["username"])                 # -> wxid_xxx 或 xxx@chatroom

nick = db.get_nickname("wxid_xxx")         # 反查昵称 / reverse lookup nickname
```

### 3.4 读取消息 / Read messages

```python
# 最近 N 条（按 sort_seq 降序）/ latest N (sort_seq desc)
msgs = db.get_messages("filehelper", limit=10)
for m in msgs:
    print(m["local_id"], m["type"], m["sender_id"], m["content"], m["create_time"])

# 单条原始行（媒体下载用，含 server_id / packed_info）/ single raw row
row = db.get_message_row("filehelper", 123)
```

消息 dict 字段 / Message dict fields：

| 字段 / Field | 含义 / Meaning |
|---|---|
| `local_id` | 消息 ID（下载媒体用）/ message ID (media download) |
| `type` | 中文类型：文本/图片/语音/视频/动画表情/文件/系统消息 |
| `sender_id` | 发送者 ID（`2` 表示自己；群聊是成员 ID）/ sender (`2` = self) |
| `content` | 内容（图片等已转换为可读摘要）/ content |
| `create_time` | 时间戳 / timestamp |
| `sort_seq` | 全局排序序号（增量监听用）/ global ordering |

### 3.5 增量消息（供轮询监听）/ Incremental messages

```python
new = db.get_new_messages("filehelper", since_seq=12345, limit=200)
```

### 3.6 按类型批量取媒体 ID / Batch media IDs

```python
# 返回该会话全部图片 local_id（不受总消息分页限制）/ all image IDs, ignores msg-limit
img_ids = db._find_media_rows("群名", {3})
# 类型码 / type codes：1文本 3图片 34语音 43视频 47动画表情 49文件
# 1 text, 3 image, 34 voice, 43 video, 47 emoji, 49 file
```

---

## 4. 实时消息监听 / Real-time Message Listening

两种方式：**db.Listener**（推荐，纯数据库轮询）和 **WeChat.AddListenChat**（wxauto 风格封装）。
Two ways: **db.Listener** (recommended, pure DB polling) and **WeChat.AddListenChat** (wxauto-style).

### 4.1 db.Listener（推荐 / recommended）

```python
from wechatauto import WeChatDB
from wechatauto.db import Listener

db = WeChatDB()
lst = Listener(db, interval=1.0)          # 每秒轮询一次 / poll every second

def on_msg(msg, lst):
    print(f"[{msg['type']}] {msg['sender_id']}: {msg['content']}")
    # 可在此扩展业务：关键词回复、媒体下载、通知推送等 / extend here

lst.add_listener("filehelper", on_msg)    # 参数是会话 username
lst.start()                               # 启动（后台线程）/ background thread
# ... 你的主程序逻辑 / your main logic ...
lst.stop()                                # 停止 / stop
```

**并发模型 / Concurrency model**：

- 轮询线程只读库 + 分派，不会被慢回调阻塞 / the poller never blocks on slow callbacks
- 每个会话一条独立工作线程：**同会话保序、跨会话并行** / per-chat worker: in-order per chat, parallel across chats
- 慢回调（AI 调用、图片识别）不影响整体监听 / slow callbacks don't affect polling

**监听无聊天记录的联系人 / Contact with no history**：消息表按需创建，对方发第一条消息后下次轮询即可捕获，只需 `add_listener("wxid_xxx", cb)`。

**watermark 持久化 / Watermark persistence**：监听器记录已消费的 `sort_seq`，下次启动可传入避免重复推送。

**跨分片读取 / Cross-shard reads**：会话消息表 `Msg_<md5>` 横跨多个 `message_*.db` 分片，`get_messages` / `get_new_messages` 已合并全部分片并按 `sort_seq` 排序，增量监听无重放。注意 `local_id` 跨分片不唯一，精确取单条时给 `get_message_row(user, local_id, local_type=类型码)`。

### 4.2 防撤回监听 / Anti-recall listener（`RecallGuard`）

```python
from wechatauto import WeChatDB, RecallGuard
from wechatauto.db import Listener

db = WeChatDB()
guard = RecallGuard(db)                    # 镜像库 + 媒体备份目录自动创建
lst = Listener(db, interval=1.0)
guard.watch(lst, backfill=50)              # 挂到监听器：镜像+备份+撤回检测一体
lst.start()
```

- 每收到一条**新消息**即写入独立镜像库（`mirror` 表），图片/语音/视频/文件附件增量备份到 `media/` 目录；
- 检测到撤回系统消息（`revokemsg`）时，终端打印 `[撤回] 撤回者 撤回了一条消息` + 原文（镜像反查窗口内最近消息）+ 媒体备份路径；
- 撤回事件记入 `recall_events` 表，事后用 `guard.get_recalled(chat=None, limit=50)` 查询；`watch(backfill=N)` 预回填当前库最近 N 条历史提升回溯成功率（历史原文常因微信本地删行已不在，能恢复多少取决于回填时机）；
- 一行式示例：`python -m wechatauto.demo_recall`（`--backlog=N` 预回填 N 条，`--all` 监听全部会话）。

### 4.2 WeChat.AddListenChat（wxauto 风格 / wxauto-style）

```python
from wechatauto import WeChat
from wechatauto.msgs import TextMessage, ImageMessage

wc = WeChat()

def on_msg(msg, chat):
    print(f"[{msg.type}] {chat.who}: {msg.content}")
    if isinstance(msg, ImageMessage):
        md = MediaDownloader(chat._db)
        out = md.download_image(chat._wxid, msg.local_id)

wc.AddListenChat(nickname="群名", callback=on_msg)   # 传昵称即可，内部解析
wc.GetListenMessage()        # 阻塞监听循环（Ctrl+C 退出）/ blocking listen loop
# 或 / or wc.KeepRunning()
```

**回调里的「谁发的」** / who sent it

`msg` 由数据库行转换而来，发送者身份分三步解析：`messages.real_sender_id`
（数字 rowid）→ `message_resource.db` 的 `SenderName2Id` → 真 wxid → `contact.db`
的备注/昵称。

```python
def on_msg(msg, chat):
    msg.sender_wxid     # 真 wxid（群消息也能拿到，不再只有文本能刮正文前缀）
    msg.sender          # 备注或昵称；解析不到时退回 wxid，再退回会话名
    msg.sender_remark   # 同上（备注优先）
    msg.wxid            # 自己发的消息 = 自己的 wxid（不再是常量 2）
    msg.attr            # 'self' / 'friend'
    msg.local_id, msg.sort_seq, msg.create_time
```

群里那些**不在你通讯录**的人只有成员表能给名字：

```python
members = chat.GetGroupMembers()   # [{username, nick_name, remark, is_owner}, ...]
wc.GetGroupMembers()               # 当前会话是群时同样可用；非群返回 []
db.get_nickname("wxid_xxx")        # 备注 > 昵称 > 原样返回
db.nickname_map()                  # 一次性 wxid→昵称 字典，带缓存（批量场景用它）
db.username_by_nickname("阿Q")      # 反查 wxid
```

> 注：`msg.sender` 在群里以前返回的是正文里的 `wxid_xxx`，现在返回昵称；需要原始
> wxid 时用 `msg.sender_wxid`。`SenderName2Id` 缺记录时仍会从正文
> `wxid_xxx:\n` 前缀兜底，所以文本消息的行为不变。
>
> 覆盖率（8 个真实群、1249 条历史消息实测）：带发送者身份 **95.8%**，非文本消息
> **99.6%**（这轮之前非文本是 0%——只能靠正文前缀）。剩下 4.2% 是微信自己没留身份的行：
> `real_sender_id` 在 `SenderName2Id` 里查不到，`source` 里也没有任何用户名标签，
> 库里造不出来的东西就不造，`msg.sender_wxid` 保持空串，`msg.sender` 退回会话名。

`WeChat` 还提供 / also offers：

```python
wc.GetSession()            # 会话列表 / session list [SessionItem]
wc.ChatWith("filehelper")  # 切换当前会话 / switch current chat
wc.GetAllSubWindow()       # 所有会话窗口 / all chat windows
```

### 4.3 监听所有会话 / Listen to every chat (`AddListenAll`)

不想一个个点名时用全局监听。/ Register one callback for **all** sessions instead of naming them.

```python
from wechatauto import WeChat

wc = WeChat()

def on_any(msg, chat):
    print(f"[{chat.nickname}] {msg.content}")
    # 需要直接回话也可以：（第一次用时才构造真正的 Chat，并缓存下来）
    # chat.SendMsg("收到")

wc.AddListenAll(on_any)      # discover=True（默认）：之后新出现的会话也自动纳管
wc.GetListenMessage()        # 或 wc.KeepRunning()
# wc.RemoveListenAll()      # 停止全局监听
```

- **和 `AddListenChat` 可以并存**：一个会话能挂多个回调。已经单独监听过的会话
  同样会收到全局回调（早期实现会跳过它们，等于全局监听漏掉最活跃那批会话）。
- `chat.who` 是会话 `username`，`chat.nickname` 是显示名；`chat.SendMsg(...)`
  走的是普通发送路线。
- 只读数据库轮询，不点界面、不抢前台，因此和 UI 自动化互不影响。
- 更底层（自定义轮询间隔、水位持久化）用 `db.Listener`：

```python
from wechatauto.db import WeChatDB, Listener
lis = Listener(WeChatDB(), interval=1.0)   # 水位默认存到 workdir/listener_watermark.json
lis.add_all(on_any, discover=True)         # 与 AddListenAll 同一套语义
lis.start(); ...; lis.stop()
```

---

## 5. 发送消息 / Sending Messages

### 5.1 快速函数 / Quick functions (guia)

```python
from wechatauto.guia import (
    quick_send, quick_send_file, quick_send_image, quick_reply,
)

quick_send("你好", "filehelper", verify=True)          # 文本，verify=True 从库回读确认
quick_send_file(r"D:\report.pdf", "filehelper")         # 文件 / file
quick_send_image(r"D:\photo.png", "filehelper")         # 图片 / image
quick_reply("回复内容", "filehelper", 123)              # 回复某条消息 / reply
```

### 5.2 WeChat / Chat 对象（wxauto 风格 / wxauto-style）

```python
from wechatauto import WeChat

wc = WeChat()
chat = wc.ChatWith("filehelper")          # 或 / or Chat("filehelper", wc._gui, wc._db)

resp = chat.SendMsg("你好")                # 发送到当前会话 / send to current chat
resp = chat.SendMsg("大家好", "群名", at=["@张三", "@李四"])  # 群聊 @ 成员 / group @members
resp = chat.SendFiles([r"D:\a.pdf", r"D:\b.docx"])          # 多个文件 / multiple files
```

### 5.3 消息对象操作 / Message objects

```python
msgs = chat.GetAllMessage()               # 全部消息 / all messages
new = chat.GetNewMessage()                # 新消息 / new messages
last = chat.GetLastMessage()              # 最后一条 / last message

for m in msgs:
    print(m.type, m.content, m.sender, m.create_time)
```

### 5.4 语音通话 / 拍一拍 / 撤回 / Voice call / Poke / Recall

```python
chat.VoiceCall()                          # 语音通话 / voice call
chat.VoiceCall(video=True)                # 视频通话 / video call
chat.Poke()                               # 拍一拍 / poke
chat.RecallLastMessage()                  # 撤回最近一条自己发的消息 / recall latest own message
```

### 5.5 转发语音 / Forward voice

```python
chat.ForwardVoiceMessage(target="群名")    # 从当前会话提取语音转成文件发送
```

### 5.6 发送的验证机制（防误发）/ Anti-misdelivery verification

`send_msg` 链路带**目标对象三重校验**（UIA 路径）/ triple target verification (UIA path)：

1. `open_chat` 打开后从 UIA 树读回输入框名称比对 / reads back input-box name after opening
2. 发送前确认 `current_chat() == 目标` / confirms current chat is the target
3. `verify=True` 时从数据库回读确认消息落库 / reads back from the DB to confirm

**目标不在好友/会话列表时安全失败**，不会误发给当前打开的会话（区别于旧版 wxauto3）。
**If the target isn't in your list, sending fails safely** — never falls back to the current chat.

---

### 5.7 拟人节奏与写动作节流 / Human pacing & write throttling (`rhythm`)

微信风控看到的是**动作的时间分布**（固定间隔、光标传送、永远命中控件正中、匀速键入、
几秒内连发），所以这层做在库里、默认生效。/ WeChat risk control sees the *time
distribution* of actions, so pacing lives in the library and is on by default.

```python
from wechatauto import rhythm
rhythm.set_profile('natural')   # 默认 / default：间隔 2.5-6s，120s 内 6 次，突发后冷却 30-75s
rhythm.set_profile('calm')      # 长时间挂机 / 真人会话：间隔 6-14s，300s 内 3 次
rhythm.set_profile('fast')      # 录屏赶时间：仍然非匀速，只是贴近原速
rhythm.set_profile('off')       # 精确还原这层之前的行为，只用于对照实验
print(rhythm.snapshot())        # 当前档位、距上次写动作秒数、窗口内计数
```

- **只管写动作**：发消息 / 发文件 / 点赞 / 评论 / 撤回 / 拍一拍 / 语音通话。读库、截图、
  OCR、定位控件不节流。/ Reads are never throttled.
- 环境变量单项覆盖（无需改代码）/ single-field overrides via env：
  `WECHATAUTO_RHYTHM=natural|calm|fast|off`、`WECHATAUTO_WRITE_GAP=秒`、
  `WECHATAUTO_WRITE_BURST=次`。
- 节流状态在 `~/.wechatauto/rhythm.json`，**跨进程生效**（每个脚本都是新进程）。档位本身
  不落盘，`rhythm.reset()` 只清计数，所以误设的 `off` 不会串到下一次会话。
- 想给某个等待加抖动：`rhythm.nap(0.5)` 而不是 `time.sleep(0.5)`——倍率下限 1.0，只会等得更久，
  不会把原来撑渲染稳定性的等待缩短。

## 6. 媒体下载 / Media Download

### 6.1 初始化与密钥 / Init & keys

```python
from wechatauto import WeChatDB, MediaDownloader

db = WeChatDB()
md = MediaDownloader(db)                       # 默认保存到 ~/Documents/wechatauto_media
# md = MediaDownloader(db, save_dir=r"D:\media")   # 指定保存目录 / specify save dir
```

图片 AES 密钥处理 / Image AES key handling：

```python
md.detect_image_key()          # 扫描进程内存提取密钥（首次需要，之后持久化）
# md = MediaDownloader(db, image_key="16位密钥")   # 或手动注入 / inject manually
```

> ⚠️ 图片 AES 密钥仅在**微信中点开图片查看**时驻留内存约 5 分钟。首次运行请先在
> 微信里点开任意一张图；`detect_image_key(monitor=True)` 可自动轮询等待；找到后
> 持久化到 `image_keys.json`，之后无需再扫。
> The image AES key is only resident while **viewing an image in WeChat** (~5 min).

### 6.2 下载 API / Download API

```python
# 按类型自动分发（3图片 34语音 43视频 49文件）/ auto-dispatch by type
out = md.download_media("filehelper", 123, save_dir=r"D:\media")

out = md.download_image("filehelper", 123)      # jpg/png/gif（旧行为）
out = md.download_image("filehelper", 123, tier="best")    # 原图>压缩版>缩略图，档位标在文件名（§6.2.2）
out = md.download_voice("filehelper", 123)      # .silk
out = md.download_video("filehelper", 123)      # .mp4
out = md.download_file("filehelper", 123)       # 原文件 / original file

# 下载原图（通过UI点击触发微信下载）/ download original image (UI click triggers download)
out = md.download_image_original("filehelper", 123, timeout=30)
```

返回落盘路径，失败返回 `None`。 / Returns the saved path, or `None` on failure.

### 6.2.1 语音取不到时，先分清是谁的问题 / Why some voices have no audio

`download_voice()` 返回 `None` 有两种完全不同的原因，以前分不出来
（issue #20「26 条语音只识别到 19 条」就卡在这个歧义上）：

```python
for v in md.list_voice_status("wxid_xxx", limit=500):
    v['available'], v['reason'], v['bytes'], v['download_status'], v['self_sent']

md.voice_status("wxid_xxx", local_id)     # 单条，字段同上
```

`reason` 取值：

| reason | 含义 | 能怎么办 |
|---|---|---|
| `ok` | 音频在 `media_*.db` 的 `VoiceInfo` 里，能取字节 | 正常下载 |
| `audio_not_downloaded` | 微信**没把这段音频落盘**（`download_status=0`） | 读库无能为力；在微信里播放一次就会落盘 |
| `audio_missing_from_media_db` | `download_status` 说该有，`VoiceInfo` 里却没有 | 这才是可能的库侧问题，值得开 issue |
| `session_not_in_media_index` | 该会话在 media 库里连 `Name2Id` 条目都没有 | 同上，通常也是没落盘 |
| `no_server_id` / `no_voice_row` | 消息行缺 `server_id` / 这条不是语音 | 数据本身的问题 |

判据来自实测：本机 20 个会话 958 条语音里，`download_status != 0` 与「音频在本地」
**一一对应，无一例外**（898 可用 / 54 未落盘 / 6 会话无索引，可用率 93.7%），
所以 `download_status` 可以直接当「微信有没有下载」的标志用；新实现与独立复算
在这 958 条上逐条一致。

> 想补齐那 6%，只能在界面上把语音播放一遍（微信随后会把 `voice_data` 写进
> `VoiceInfo`）。那属于驱动真实客户端的写动作，要走 `rhythm`，本库没有自动化它。

### 6.2.2 图片有三档，先问清楚本机有没有原图 / Which image tier is on this machine

一条图片消息在 `msg/attach/<md5(会话)>/<YYYY-MM>/` 下最多落三个文件。**先把三层说清楚，
「原图」这个词两种意思都有人在用**：

| 文件 | 是什么 | 什么时候落盘 |
|---|---|---|
| `<md5>_t.dat` | **预览图**（缩略图） | 收到消息就有 |
| `<md5>.dat` | **完整图**（微信默认下发的那一份，多数人口中的「原图」其实是它） | 点开过 / 收的时候本机就有 |
| `<md5>_h.dat` | **原件**（发的时候勾了「原图」才有的那份） | 只有勾了原图、或点过「查看原图」 |

「只能下到缩略图、下不到原图」的反馈基本都出在这三档的歧义上——以前
`download_image` 压根不看 `_h.dat`，而且拿到完整图时文件名和原件一模一样，
调用方只能靠大小猜，于是反复重试。

```python
out = md.download_image("群名", 123, tier="full")       # 只要「非预览图」：原件 > 完整图
out = md.download_image("群名", 123, tier="original")   # 只要原件，没有就 None，不降级
out = md.download_image("群名", 123, tier="best")       # 原件 > 完整图 > 预览图
out = md.download_image("群名", 123)                    # 不传 tier = 旧行为，逐字不变
```

| tier | 取哪一档 | 落盘文件名 | 本机没有时 |
|---|---|---|---|
| `None`（默认） | 完整图 → 预览图 | `<user>_<lid>.jpg` / `..._thumb.jpg` | 退预览图 |
| `'original'` | 只有 `_h.dat`（原件） | `..._h.jpg` | `None`（**不悄悄降级**） |
| `'full'` | 原件 → 完整图，**绝不用预览图交差** | 按档位标 `_h` / 无 | 让微信去下（点开预览那一步本身就会下 `.dat`），下完还没有才 `None` |
| `'best'` | 原件 → 完整图 → 预览图 | 按档位标 `_h` / 无 / `_thumb` | `None` |
| `'mid'` / `'thumb'` | 只要这一档 | 无 / `_thumb` | `None` |

**要「一张完整图」的调用方应该用 `'full'` 而不是 `'original'`**：`'original'` 要的是
勾了原图那一档，本机多数图根本没有（下面那节有实测数）；`'full'` 在本机有货时一步界面
都不碰，只有连完整图都没下过时才驱动界面去下。

批量前先问一遍，别逐条试：

```python
for im in md.list_image_status("wxid_xxx", limit=300):
    im['reason'], im['best'], im['tiers'], im['local_id']

md.image_status("wxid_xxx", local_id)      # 单条，字段同上
```

| reason | 含义 | 能怎么办 |
|---|---|---|
| `ok` | `_h.dat`（原件）在、不是空壳；`verify=True` 时还要求解密后结构完整 | `tier='original'` 直接拿 |
| `mid_only` | 有**完整图** `.dat`，只是没有原件那一档（`has_full=True`） | 要一张完整图直接 `tier='full'`/`'best'`，一步界面都不碰；别人发的图想要原件可以 `download_image_original()` 去追；**自己发的图本机一般没有更大的一档**（见下表），追也追不到 |
| `only_thumbnail` | 只有预览图（群聊图从没点开过，`has_full=False`） | `tier='full'` 会驱动界面让微信把完整图下下来；`download_image_original()` 也行 |
| `original_partial` | 有 `_h.dat` 但是空壳（<1KB），或 `verify=True` 时解密后**缺 JPEG/PNG 收尾标记**（下到一半） | 再触发一次 |
| `no_local_copy` / `no_md5` / `no_message_row` | 目录里一份都没有 / 取不到图片指纹 / 这条不是图片 | 核对 `local_id` 与账号目录 |

「原图下好了没」看的是**结构和空壳**，不是尺寸比例：非空、≥1KB；`image_status(..., verify=True)`
会再解密看一眼有没有 `FF D9` / `IEND` 收尾（批量接口不要开，那等于把每张原图都解一遍）。
**两代按尺寸猜的判据都被实测否掉了**：

- 1.2.4.2 之前是 `> 102400`：本机 705 个 `_h.dat` 中位数只有 91.5KB、51.3% 在 100KB 以下，
  一半真原图被当成「还没下载」。
- 1.2.4.2 换成「不比压缩版小 10% 以上」，**用户实机证明这条也是错的**：同一张图的 `.dat`
  有时就是比 `_h.dat` 大（实测 h/mid 有 0.55、0.82 的，两种编码各存一份），于是真原图又被
  判成没下完，代码去点「图片原始大小」——而那颗按钮在查看器里只是切显示缩放，
  原图本来就在盘上时点了自然没有任何反应。

正在下载中的截断由 `_wait_h_dat` 的「大小不再变化」轮询负责，不靠尺寸猜。

本机 211 个会话 4825 条图片消息的实测分布（每会话取最近 400 条）：`mid_only` 2410、
`only_thumbnail` 1773、`ok` 636、`original_partial` 3（三条都是 <1KB 的空壳）、
`no_local_copy` 3。也就是说**多数图片本来就没有原图可下**（每 7 条里只有 1 条有），
这是微信的存储策略，不是解密失败；先查状态再决定要不要触发下载，能省掉大量无效重试。

**按发送方拆开看，差距非常大**（同一次扫描，按 `real_sender_id` 是不是本机账号分类）：

| 发送方 | 条数 | 有 `_h.dat` | 只有压缩版 `.dat` | 只有缩略图 |
|---|---|---|---|---|
| 我自己发的 | 554 | **19（3.4%）** | 527（95.1%） | 8 |
| 别人发的 | 3401 | 611（18.0%） | 1594 | 1192 |

而且**那 19 条自发图片的 `_h.dat` 全都没有同名的 `.dat`**（别人发的 617 个 `_h.dat` 里
373 个是两档都有的）。合起来读就是一句话：**自己发出去的图，只有当时勾了「原图」才在
本机留下原件；没勾的话本机最好的一份就是那个 `.dat`，微信没有更大的原件可下**。
所以「我发的图片提示找不到原图」是事实陈述，不是 bug——现在这种情况会**直接返回 `None`
并提示改用 `tier='best'`，不再为它去点一轮界面**（连 `.dat` 都没有的那种例外：打开预览
会让微信把压缩版下载下来，所以还是要走界面）。
尺寸上也印证：自发图 `.dat` 中位 60KB／最大 770KB，别人发的 `.dat` 中位 58KB，
而 `_h.dat` 中位 66KB、p75 351KB、最大 15MB——**中位数这么小，任何按绝对大小的
判据都会误杀**。

### 6.3 群聊图片 / Group chat images

- 群聊图片原图**只有点开查看过才落盘**；否则只有缩略图 / originals only stored after being opened
- `download_image` 会自动回退缩略图，文件名带 `_thumb` 标记 / auto-falls back to thumbnail (`_thumb`)；
  不想回退就传 `tier='original'`，本机没有原图时返回 `None`（见 §6.2.2）
- `download_image_original` 通过UI自动化点击图片消息触发微信下载原图 / `download_image_original` triggers download via UI click
  - 本机已经有合格 `_h.dat` 时**直接解密落盘，不动界面** / a valid `_h.dat` already on disk is decrypted without touching the UI
  - 会切到对应会话；目标那条图**不在可视区时会按数据库算出的行差滚过去**（`scroll=True`，默认开；`scroll=False` 就只在当前屏上找，绝不动界面）
  - **「哪一行才是这条图」用数据库定位**：可视区里文本行的 `Name` 就是真实正文（会被截断，所以按前 10 字互相包含来比），图片行的 `Name` 恒为「图片」，整段序列与数据库的「文本/图片」序列滑窗对齐，对得上就直接点名目标行。三道门槛缺一不可：
    - 至少**两条文本锚点**且吻合度 ≥0.6——实机撞过可视区只剩一行时「吻合度 1.00」的假高分，那种情况任何偏移都算完美吻合，等于没有信息；
    - **并列最优偏移必须给出唯一答案**。「T I I T」这种形状在整段历史里会重复出现，多个偏移同时满分是常态；只要并列偏移对「目标是第几行」答案不同就拒绝动手（`_align_window` 会把 `ties` 全部交出来）；
    - 对齐结果那一行在 UIA 里**确实是图片行**。
  - 滚过去的步长是**实测出来的**：先按「每格 1 行」假设滚，滚完看对齐偏移真的挪了几行再修正每格行数，所以不同 DPI、不同窗口高度都不需要预设常量。滚轮走 `moment._send_scroll`（先置前台 + 落点归属校验：曾经有一次自检把滚轮打进了压在微信上面的 IDE），发不出去就报 `scroll-blocked`，滚了但纹丝不动报 `scroll-stuck`，滚满 `max_scrolls`（默认 6 轮）报 `scroll-limit`——**不会无限滚**。认不出时退回「数它下面压了几张更新的图」，再不行逐个试
  - 类名映射是**对着数据库逐行核过的**，别按直觉改：`mmui::ChatTextItemView` 才是文本行；`mmui::ChatBubbleItemView` 是文件/链接/卡片（库里正文近 1900 字 XML，UIA 只给 43 字摘要），把它当文本行会把整段对齐带偏；`mmui::ChatItemView` 是时间行、`mmui::ChatSystemInfoItemView` 是系统消息——两侧同时都不参与对齐
  - **点气泡仍然只能用坐标**：`mmui::ChatBubbleReferItemView` 在 UIA 里是**叶子行**（用原始视图 `ControlFromPoint` 从行首横扫到 80% 行宽，返回的始终是这一行本身，没有缩略图子控件），而它虽然挂着 `InvokePattern`，**Invoke 是空操作**（实机 0 预览窗起步、Invoke 后 8 秒不出现，和 4.1.15 那个搜索按钮的 `Invoke()` 空操作同一个形状）。所以行矩形是**整行宽**（实测 2598px），缩略图只占其中 `+1.7%~+24.3%`
  - **自己发出的图气泡在右边**：只按「左边缘 +12%」点就会点空——这是「点击打开图片时错位」最直接的一种形状。现在按发送方决定先点哪一侧，第一侧没点开再点该行另一侧
  - **「是不是我发的」不写死常数**：`real_sender_id` 是 `message_resource.db` 里 `SenderName2Id` 的 rowid，**本机账号落在哪个 rowid 每台机器不一样**。代码原本写死 `== 2`（1.1.8 从别人那台机器带来的取值），本机实测自己是 **1**：文件传输助手 400 条消息全是 `sender_id=1`，`SenderName2Id` 里解析成本机 wxid 的 rowid 也是 1，而 `2` 是某个常联系的好友（图片消息里 512 条）。按常数判的代价很直接——自己发的图被当成别人发的，先去点左边，永远点不中气泡，看起来就是「我发的图片提示找不到原图」。现在按「解析出来等不等于本机 wxid」判，索引查不到时才兜底按 1
  - 「有没有点开」只把**新出现**的预览窗算作成功（按 `NativeWindowHandle` 分辨）；屏幕上本来就开着预览窗时会先警告一句，因为旧窗口会被误判成刚点开的
  - **预览窗有两种形状**（同一台机、同一版本实测都出现过）：① 桌面的直接子节点就是 `mmui::PreviewWindow`；② 顶层是 `Qt51514QWindowIcon`、标题「图片和视频」，`mmui::PreviewWindow` 在**它里面一层**。只按「顶层子节点的类名含 PreviewWindow」筛，第 ② 种永远找不到——表现就是「点了没反应 / 按钮点不对」，而实际一次都没走到找按钮那步
  - 预览窗工具栏按钮全是真 UIA 控件，按名字取：`置顶 / 上一张 / 下一张 / 预览 / 放大 / 缩小 / 图片原始大小⇄图片适应窗口大小 / 旋转 / 编辑 / 翻译 / 提取文字 / 保存 / 更多`，加标题栏 `最小化 / 最大化 / 关闭`
  - **那颗缩放键的 Name 会随显示状态变**（实测同一颗按钮在「图片原始大小」和「图片适应窗口大小」之间切换）。只写死一个名字找，找不到就提前返回 → 「保存」兜底根本没机会跑，用户看到的就是「点了缩放那颗，没点下载那颗」。现在按**两个候选名**找，并且**只有当前是「图片原始大小」时才点它**（已是「图片适应窗口大小」说明原件就在显示中，再点只会缩回去，直接走「保存」）
  - **真正下载原件的是「保存」**（↓ 图标，在缩放那颗 ▣ 的右边）。找不到缩放键**不再提前返回**，一律继续走「保存」
  - `download_image_original(..., want='mid')` 是给「只要非预览图」用的：等的是 `.dat` 那一档、**不点缩放键**（点它才会去追原件）、点完界面解密出来的也是 `.dat`。`tier='full'` 本机没货时走的就是这条
  - **批量下载同一会话的多张图不再反复搜索进入**：进函数先读当前会话标题（`current_chat()`，取自输入框的 Name——它一直是会话标题而不是正文），已经是目标会话就跳过搜索；读不到标题时保守照常进入
  - 滚动有一个硬前提：**拿得到微信进程 id**。拿不到就退化成「只认当前屏、绝不滚」（`max_scrolls=0`）并打一条警告——落点无法校验时滚轮可能打进压在微信上面的别的程序
  - 点完之后是**轮询等** `_h.dat` 出现并停止变大（到 `timeout` 为止），不再固定睡 3 秒取一次
  - 点击坐标依赖 WeChat 4.x 的 `mmui::ChatBubbleReferItemView` 布局（DPI 感知进程下按物理像素定位），不同窗口宽度/DPI 用相对偏移自动适配 / click coords rely on the `mmui::*` layout (physical pixels under a DPI-aware process); relative offset adapts to window width/DPI
  - 预览窗口内的「图片原始大小」按钮是完整 UIA 控件，用 `Click()` 点击 / the preview-window button is a real UIA control and is clicked via `Click()`
  - **「图片原始大小」点了没反应时改点「保存」兜底**：那颗按钮本质是查看器的缩放档，原图已在盘上（或这张根本没有更大的原件）时它不触发任何下载。所以 `_h.dat` 等不出来之后，会点预览窗的「保存」。**实机确认「保存」不是静默落盘，而是弹 Windows 通用保存对话框**：顶层类名 `#32770`，**标题是「保存」而不是「另存为」**（按标题里有没有「另存」去匹配会认不出，现在按「`#32770` + 里面真有一颗以「保存」开头的按钮」认）；默认目录是 `<账号>\temp\InputTemp`，**路径不固定**，文件名预填 `微信图片_<时间戳>_*.jpg`
  - 对话框里的控件形状（逐层 dump 出来的）：`ComboBox name='文件名:'` 里面那层 `Edit name='文件名:'` 才是可写值的——**命中容器还要再往里找 Edit**，直接对外层 ComboBox `SetValue` 是写不进去的；右上角还有一颗 `SearchEditBox name='搜索框'` 的 Edit，**拿「第一个 Edit」会填到这里**；按钮文案带助记符（`保存(S)` / `取消`），所以按前缀匹配。填目标全路径用 `ValuePattern.SetValue`、点按钮用 `InvokePattern.Invoke`，**全程不发键盘**
  - **任何失败路径都会点「取消」把模态框关掉**——那是模态窗，不关掉就一直压着预览窗，后面每张图都点不到。遍历对话框时 UIA 节点可能在中途失效（切页/关窗），坏一颗就跳过那一支，不能让异常把整条兜底路线打死
  - 万一以后版本改成静默保存，仍保留「点之前拍快照、点之后找新文件」的收法（快照只走「最近改过」的目录，不整树扫）。两条路都不通才返回 `None`
  - **「保存」拿到的那份不在加密附件树里，`image_status` 永远看不见它**：`image_status` 只看 `msg/attach/<md5(会话)>/<月份>/` 下的 `_t.dat`/`.dat`/`_h.dat` 三档，「保存」写出去的是明文字节（默认落在 `temp\InputTemp`，用户手点的话落在你随手选的那个文件夹）。所以「我之前明明保存过，怎么还提示取不到原图」不是查错了目录——那一档本来就不存在。要「本机最好的那份」用 `download_image(tier='best')`，它直接从 `.dat` 解密，一步界面都不碰
  - 预览窗里找不到「图片原始大小」按钮（这张本来就是原图／微信没给这个入口）会**明确警告并返回 `None`**，指引改用 `tier='best'`，不再和「下载没完成」混成同一种失败
- 无 ffmpeg 时 wxgf 格式存为 `.wxgf` 原始数据兜底 / without ffmpeg, wxgf saved as `.wxgf`

### 6.4 批量下载全部图片 / Batch download all images

```python
ids = db._find_media_rows("群名", {3})   # 全部图片 ID，不管会话消息总量多大
for lid in ids:
    out = md.download_image("群名", lid)
    if out:
        print("downloaded:", out)
```

命令行也有现成脚本 / There is also a CLI demo：

```bash
python demo_media.py 群名 --images 100        # 下载该群最近 100 张图片
python demo_media.py 群名 --images 100000     # 超过总数即全部 / all if > total
python demo_media.py 文件传输助手 --filter 图片,文件
```

---

## 7. 朋友圈 / Moments

```python
from wechatauto import MomentDB

moments = MomentDB(db)                        # 基于 sns.db 直读 / direct sns.db reads
for feed in moments.get_moments(limit=10):
    print(feed["nickname"], feed["text"])
    print("  images:", [i["md5"] for i in feed["images"]])
    print("  likes:", [l["nickname"] for l in feed["likes"]])
    print("  comments:", [(c["nickname"], c["content"]) for c in feed["comments"]])
    # 下载本条动态的图片/视频（优先本地缓存，其次 CDN url）/ download media
    saved = moments.download_moment_media(feed, save_dir=r"D:\moments")
    print("  saved:", saved)
```

朋友圈图片/视频下载的完整命令行示例见 `wechatauto/demo_moments_download.py`
（`python -m wechatauto.demo_moments_download [N] --out 目录`）。

**点赞 / 评论（UIA 控件路线）**：点赞/评论属服务端行为，需走界面（数据库路线只读）。
`WeChat` 会热激活 `mmui` UIA 树并点击导航栏“朋友圈”后，基于 UIA 控件操作：

```python
from wechatauto import WeChat

wx = WeChat()
moments = wx.Moment                 # UIA 树不可用时为 None
if moments is None:
    raise SystemExit("UIA 树不可用，无法点赞/评论")
wx.SwitchToMoments()                # 点击导航栏“朋友圈”
items = moments.GetMoments()
moments.Like(items[0])                            # 点赞
moments.Like(items[0], cancel=True)               # 取消赞
moments.Comment(items[0], "不错！")                # 评论
moments.Comment(items[0], "谢谢！", reply_to="张三")   # 回复某人评论
```

命令行示例：`python -m wechatauto.demo_moments_interact [--like N | --unlike N | --comment N 文字]`
（直接运行则只列出最新动态，不操作界面）。

---

## 8. 多账号 / Multi-account

```python
from wechatauto import list_accounts, WeChatDB

accts = list_accounts()                       # 列出本机所有微信账号 / list all accounts
for a in accts:
    print(a)

db = WeChatDB(account="wxid_xxx")             # 指定账号 / pick an account
```

---

## 9. 导出聊天记录 / Exporting Chat History

```python
db.export_history(
    out_dir=r"D:\export",
    out_format="json",        # json / sqlite
    include_media=True,
)

for chat in db.list_message_chats():          # 有消息的会话 / chats that have messages
    print(chat)
```

---

## 10. 群聊操作专题 / Group Chat Operations

### 10.1 获取群信息 / Group info

```python
info = chat.ChatInfo()                        # 群成员、群主等 / members, owner, etc.
```

### 10.2 群聊发消息并 @ 成员 / Send & @ members

```python
chat.SendMsg("大家看这个", at=["张三", "李四"])
# 或指定群 / or
wc.ChatWith("群名")
wc.SendMsg("开会了", at=["全体成员"])
```

### 10.3 群聊监听 / Listen to a group

```python
lst.add_listener("44054166277@chatroom", on_msg)   # 用群 username
```

### 10.4 群聊图片 / 语音 / Group images & voice

```python
md.download_image("群名", local_id)      # 自动缩略图回退 / auto thumbnail fallback
md.download_voice("群名", local_id)      # 自动搜索所有 media_*.db / searches all media_*.db
```

---

## 11. 常见问题与排错 / FAQ & Troubleshooting

### Q1: `RuntimeError: 数据库无可用密钥` / no usable DB key

- 确认微信**已登录**（密钥在进程内存）/ make sure WeChat is **logged in**
- 确认运行账号有权限读取微信进程（同用户运行）/ run as the same user
- 微信版本差异可能影响内存扫描，升级微信或查看 issue / some versions differ in memory layout

### Q2: 图片下载失败 / 无法获取 AES 密钥 / image key not found

- 先在微信里**点开一张图片看大图**，立即重试 / open any image in WeChat first
- 或 `md.detect_image_key(monitor=True)` 持续等待
- 或手动传 `image_key="16位"` 给 `MediaDownloader`

### Q3: 群聊图片只有几张 / 很多下不了 / group chat only a few images

- 群聊图片原图未点开查看时只有缩略图，`download_image` 会自动回退
- 若要全部，用 `_find_media_rows` + 遍历（6.4），或用 `--images` 参数
- **1.2.4.2 起先问一句「本机到底有哪一档」**：`md.list_image_status(user)` /
  `md.image_status(user, local_id)` 给每条图片 `tiers`（三档字节）/ `best` /
  `reason`。`only_thumbnail`、`mid_only` 是微信的存储策略（原图从没点开过），
  不是解密失败；`original_partial` 才是原图下载中断 / `list_image_status()`
  tells you which tier actually exists before you retry anything
- 只想要原图就写 `download_image(user, lid, tier='original')`：没有原图时返回
  `None` 而不是悄悄给你压缩版；想要「能拿到的最好一档」用 `tier='best'`，
  档位会标在文件名上（`_h` / 无 / `_thumb`）

### Q4: 发送失败 / sending fails

- 微信窗口需可见（不能锁屏/最小化到托盘）/ window must be visible
- 锁屏或窗口不可响应时发送会安全失败
- 换用 `verify=True` 获得回读确认

### Q5: 语音下载不到 / voice not downloading

- 1.1.4+ 已支持搜索所有 `media_*.db`（微信分片存储）/ 1.1.4+ searches all media_*.db
- **1.2.4.1 起先问一句「到底为什么」**：`md.list_voice_status(user)` /
  `md.voice_status(user, local_id)` 会给每条语音 `available` / `bytes` /
  `download_status` / `reason`。`reason=audio_not_downloaded` 表示微信没把这段音频
  落盘（在界面里播放一次即可），`audio_missing_from_media_db` 才是可能的库侧问题
  / `list_voice_status()` tells you *why*: not-downloaded vs a real lookup bug

### Q6: 监听无聊天记录的联系人 / contact with no history

- 消息表按需创建，对方发第一条消息后轮询即捕获
- 需要知道对方 wxid（用 `search_contact`）

### Q7: `WeChatAuto` 导入报错 / ImportError

- 本库入口类是 **`WeChat`**，不存在 `WeChatAuto`
- 教程代码若用旧类名，把 `WeChatAuto()` 换成 `WeChat()`

### Q8: 「控件树被屏蔽」/ UIA tree is empty

先分清两件事：**微信自绘界面，UIA 树只有在 Qt accessibility gate 打开后才存在**，
而那个 gate 是 `Weixin.dll` 在进程里的一个字节，微信**每次重启/更新/重登都会归零**。
所以它不是被谁屏蔽，而是没人写它的时候树就不存在。库在每次走 UIA 入口时会自己热写并校验
（日志：`热激活 UIA：PID=… Weixin.dll+0x…: 0 -> 1`）。

判据（一行）：看微信窗口的 ClassName —— `mmui::MainWindow` = 树在；
`Qt51514QWindowIcon` = 树没建 / class is `Qt51514QWindowIcon` means no tree。

扫不到可用窗口时，库现在会明确警告原因（每种原因一个进程只说一次，不刷屏）：

| 警告里的说法 | 真实原因 |
|---|---|
| 没扫到可见的微信主窗口 | 微信未启动/未登录/最小化到托盘，或标题变了 |
| 扫到 N 个窗口但都定位不到 Weixin.dll，**32 位** | 32 位 Python 无法枚举 64 位进程模块，换 64 位 Python |
| 同上但是 **64 位** | 权限/完整性级别不一致（别「以管理员运行」）或安全软件拦进程读取 |
| `pywin32` 不可用 | 没装 pywin32，UIA 路线整条不可用 |

热激活本身失败的三种日志原文分别对应：`不支持的 Weixin.dll 版本路径`（新版本 gate RVA
漂移且扫不出候选，需要加 RVA）、`无法打开 Weixin.exe PID`（权限/安全软件）、
`N 个候选均未使 mmui 树物化`（写进去了但 Qt 不建树）。
另外：跑在没有交互桌面的会话里（服务、非交互计划任务、RDP 已断开）永远不会有树。

---

## 12. API 速查表 / API Quick Reference

### WeChatDB（数据读取 / data）

| 方法 / Method | 说明 / Description |
|---|---|
| `get_self_info()` | 当前账号信息 / current account info |
| `get_sessions(limit)` | 会话列表 / session list |
| `search_contact(kw)` | 搜索联系人 / search contacts |
| `get_nickname(user)` | 反查昵称 / reverse nickname lookup |
| `get_messages(user, limit, offset)` | 最近消息（跨分片合并，sort_seq 降序）/ recent (cross-shard) |
| `get_message_row(user, local_id, local_type=None)` | 单条原始行（跨分片；类型码定位分片）/ single row |
| `get_message_rows_for_media(user, local_id)` | 该 id 全部 shard 行 / all shard rows for an id |
| `get_new_messages(user, since_seq)` | 增量消息（跨分片，watermark 无重放）/ incremental |
| `_find_media_rows(user, types)` | 按类型取全部媒体 ID / all media IDs by type |
| `list_message_chats()` | 有消息的会话 / chats that have messages |
| `export_history(...)` | 导出聊天记录 / export history |
| `list_accounts()` | 列出账号（模块级）/ list accounts (module-level) |

### Listener（实时监听 / realtime）

| 方法 / Method | 说明 / Description |
|---|---|
| `add_listener(user, cb)` | 注册回调 / register callback |
| `remove_listener(user, cb)` | 移除回调 / remove callback |
| `start()` / `stop()` | 启停 / start / stop |
| `watermark` | 已消费序号 / consumed seq |

### MediaDownloader（媒体 / media）

| 方法 / Method | 说明 / Description |
|---|---|
| `detect_image_key(monitor)` | 提取图片密钥 / extract image key |
| `download_image(user, lid, tier)` | 图片（三档：`_h.dat` 原图 / `.dat` 压缩 / `_t.dat` 缩略图；wxgf 转码）/ image, 3 tiers |
| `download_image_original(user, lid, timeout, min_bytes)` | 触发微信下载原图并等它落盘（本机已有合格 `_h.dat` 时不动界面）/ trigger & wait for the original |
| `image_status(user, lid)` | 单条图片本机有哪一档 + 原因 / which tier exists |
| `list_image_status(user, limit)` | 整个会话的档位一览（§6.2.2）/ per-session tier report |
| `download_voice(user, lid)` | 语音 .silk / voice |
| `voice_status(user, lid)` | 单条语音取不到的原因 / why a voice has no audio |
| `list_voice_status(user, limit)` | 整个会话的语音可用性一览（§6.2.1）/ per-session voice report |
| `download_video(user, lid)` | 视频 .mp4 / video |
| `download_file(user, lid)` | 原文件 / original file |
| `download_media(user, lid)` | 按类型自动分发 / auto-dispatch by type |

### RecallGuard（防撤回 / anti-recall）

| 方法 / Method | 说明 / Description |
|---|---|
| `RecallGuard(db, mirror_dir, media_dir, window=120)` | 镜像库目录 / 媒体备份目录 / 回溯窗口 |
| `watch(listener, users=None, backfill=50)` | 挂到 Listener（users=None 监听全部会话）/ attach |
| `backfill(user, limit)` | 手动补镜像历史 / pre-fill mirror |
| `get_recalled(chat=None, limit=50)` | 查询撤回事件 / query recall events |
| `close()` | 关闭镜像库 / close |

### WeChat / Chat（发送，wxauto 风格 / sending）

| 方法 / Method | 说明 / Description |
|---|---|
| `ChatWith(who)` | 切换会话 / switch chat |
| `SendMsg(msg, who, at)` | 发文本（支持群 @）/ send text |
| `SendFiles(paths, who)` | 发文件 / send files |
| `GetAllMessage()` / `GetNewMessage()` | 读消息 / read messages |
| `VoiceCall(video)` | 语音/视频通话 / voice/video call |
| `Poke()` | 拍一拍 / poke |
| `RecallLastMessage()` | 撤回最近消息 / recall latest message |
| `ForwardVoiceMessage(target)` | 转发语音 / forward voice |
| `AddListenChat(nickname, cb)` | 监听（WeChat）/ listen |
| `KeepRunning()` | 阻塞保持运行 / block & stay alive |

### guia（快捷函数 / convenience）

| 函数 / Function | 说明 / Description |
|---|---|
| `quick_send(text, who, verify)` | 发文本 / send text |
| `quick_send_file(path, who)` | 发文件 / send file |
| `quick_send_image(path, who)` | 发图片 / send image |
| `quick_reply(text, who, msg_id)` | 回复消息 / reply to a message |

### 消息对象 / Message objects (msgs)

`TextMessage` `ImageMessage` `VoiceMessage` `VideoMessage` `FileMessage`
`QuoteMessage` `LinkMessage` `LocationMessage` `SystemMessage` `FriendMessage` `SelfMessage`

常用属性 / Common attributes：`.type` `.content` `.sender` `.create_time` `.local_id`

---

## 参考 / References

- [README（英文 / English）](README.md)
- [README（中文 / 中文）](README.zh-CN.md)
- `wechatauto/demo_*.py` —— 各功能的可运行示例 / runnable demos