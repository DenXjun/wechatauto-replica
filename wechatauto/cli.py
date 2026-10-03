# -*- coding: utf-8 -*-
"""一条命令的常用入口：``python -m wechatauto <子命令>``。

存在的理由（issue #31「能不能把代码调用搞简单一点？太麻烦了，比如一条命令」）：能做的事
分散在 ``WeChatDB`` / ``MediaDownloader`` / ``WeChatGUI`` / ``MomentDB`` 四个对象上，
新用户得先搞清三件坑才跑得动——① 读库要传 username、驱动界面要传显示名（传错的表现为
搜索不命中，白等几十秒）；② 下载图片前得先有图片 AES 密钥；③ 保存目录要自己给。
这里把这三件事一次做完，**原有接口一字未改**：本模块只是这些接口的调用方，
不喜欢命令行的人照旧直接用那些对象。
"""
import argparse
import io
import json
import os
import sys


def _version():
    """版本号延迟到用时再取。

    ``from wechatauto import __version__`` 会连带把 ``guia``（UI 自动化那一整套）在
    import 时就拉进来——issue #8 报的就是「import 就把微信窗口激活/阻塞」这一类，
    命令行读个库不该碰界面。
    """
    import wechatauto
    return wechatauto.__version__

# 消息类型在库里是中文名（``文本`` / ``图片`` …），但用户在命令行里更可能打英文，
# 两种都收；否则「--type image 查不到」会被读成「这个会话没有图片」。
_TYPE_ALIASES = {
    "text": "文本", "文本": "文本",
    "image": "图片", "pic": "图片", "图片": "图片",
    "voice": "语音", "audio": "语音", "语音": "语音",
    "video": "视频", "视频": "视频",
    "file": "文件/链接/卡片", "文件": "文件/链接/卡片",
    "link": "文件/链接/卡片", "card": "文件/链接/卡片",
    "sticker": "动画表情", "表情": "动画表情",
    "system": "系统消息", "系统": "系统消息",
    "redpacket": "红包", "红包": "红包",
}


def _utf8_stdout():
    """Windows 控制台默认 GBK，中文正文和箭头会直接 UnicodeEncodeError。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _die(msg, code=1):
    print("× %s" % msg)
    return code


def _db():
    from wechatauto import WeChatDB
    try:
        return WeChatDB()
    except Exception as e:
        raise SystemExit(_die(
            "打不开微信本地库：%s: %s\n"
            "  先确认微信已登录；再跑 `python -m wechatauto doctor` 看密钥。"
            % (type(e).__name__, e)))


def resolve_chat(db, who):
    """把用户给的任意一种写法补成 ``(username 给读库, display 给界面)``。

    这是 issue #31 那类「调用麻烦」的核心：``get_messages`` 认 username，而搜索框
    只认昵称/备注/微信号，拿 wxid 去搜永远不命中，表现成「白等几十秒然后返回 None」。
    """
    who = (who or "").strip()
    if not who:
        return "", ""
    if who == "filehelper" or who.endswith("@chatroom") or who.startswith("wxid_"):
        display = ""
        try:
            display = db.get_nickname(who) or ""
        except Exception:
            display = ""
        return who, (display or who)
    # 给的是显示名：先按昵称/备注/微信号查 username
    try:
        hits = db.search_contact(who) or []
    except Exception:
        hits = []
    exact = [h for h in hits if who in (h.get("nick_name"), h.get("remark"))]
    if len(exact) == 1:
        return exact[0]["username"], who
    if len(exact) > 1:
        raise SystemExit(_die(
            "「%s」同时是 %d 个联系人的昵称/备注，请改用 wxid 或群号"
            % (who, len(exact))))
    try:
        for s in db.get_sessions(limit=300):
            if s.get("username") == who:
                return who, who
    except Exception:
        pass
    # 查不到也照原样传下去：群名不在通讯录里是常态（只有群成员表有），
    # 读库那条路用的是 name2id，不依赖 contact.db。
    return who, who


def _body(m):
    """正文一行话。视频/文件/引用这类正文是整段 XML，直接打出来满屏都是标签。"""
    b = (m.get("content") or "").replace("\n", " ")
    if b.startswith("<?xml") or b.startswith("<msg>"):
        import re
        txt = " ".join(re.sub(r"<[^>]+>", " ", b).split())[:80]
        if not txt:
            # videomsg / appmsg 这一类信息全在属性上，刮标签刮不到东西
            at = dict(re.findall(r'\b(\w+)="([^"]{1,40})"', b))
            txt = " ".join("%s=%s" % (k, at[k]) for k in
                           ("playlength", "length", "size", "title", "des")
                           if k in at)[:80]
        return ("[非文本正文] %s" % txt).strip()
    return b[:400]


def _fmt_line(m, sender=""):
    t = m.get("create_time")
    try:
        import datetime
        t = datetime.datetime.fromtimestamp(float(t)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        t = str(t)
    who = sender or m.get("sender_username") or ""
    return "%s %s%s" % (t, ("%s: " % who) if who else "", _body(m))


# ------------------------------------------------------------------ 子命令
def cmd_doctor(args):
    from wechatauto import WeChatDB
    print("wechatauto %s | Python %s (%d 位) | %s"
          % (_version(), sys.version.split()[0],
             64 if sys.maxsize > 2 ** 32 else 32, sys.platform))
    try:
        db = WeChatDB()
    except Exception as e:
        return _die("没有可用账号/库（微信登录了吗？）：%s: %s"
                    % (type(e).__name__, e))
    ok = sum(1 for rel, _, _ in db._db_files if db._key_works(rel))
    print("账号：%s（wxid %s）" % (db.account, db.wxid or "未取到"))
    print("数据库密钥：%d/%d 个库可解密" % (ok, len(db._db_files)))
    if not ok:
        print("  → 一个都解不开：微信要正在运行且已登录；32 位 Python 请换 64 位。"
              "深挖跑 `python -m wechatauto.diagnose_keys`")
    from wechatauto.media import MediaDownloader
    md = MediaDownloader(db)
    try:
        key = md.detect_image_key()
    except Exception as e:
        key = None
        print("图片密钥：探测抛错 %s" % type(e).__name__)
    print("图片密钥：%s" % ("已拿到（已缓存，之后离线可用）" if key else "没有——图片下不了，"
                          "在微信里点开任意一张图后重试"))
    from wechatauto.uia_driver import WeChatUIA
    uia = WeChatUIA()
    try:
        live = uia.is_materialized()
    except Exception:
        live = False
    print("控件树（发消息/下载原图要用）：%s" % ("已物化" if live else
          "拿不到——微信需要热激活一次，见 GUIDE §「控件树被屏蔽」"))
    return 0 if ok else 1


def cmd_sessions(args):
    db = _db()
    rows = db.get_sessions(limit=args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for s in rows:
        try:
            name = db.get_nickname(s["username"]) or s["username"]
        except Exception:
            name = s["username"]
        print("%-28s 未读 %-3s %s" % (name[:26], s.get("unread"),
                                      (s.get("summary") or "")[:40]))
    print("共 %d 个会话" % len(rows))
    return 0


def _messages(db, who, limit, offset, type_filter):
    user, display = resolve_chat(db, who)
    rows = db.get_messages(user, limit=limit, offset=offset) or []
    if type_filter:
        want = _TYPE_ALIASES.get(type_filter.lower(), type_filter)
        rows = [r for r in rows if r.get("type") == want]
    return user, display, rows


def cmd_messages(args):
    db = _db()
    user, display, rows = _messages(db, args.chat, args.limit, args.offset,
                                    args.type)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    own = getattr(db, "wxid", "") or ""
    for m in reversed(rows):                     # 终端里自上而下按时间正序
        sender = "" if m.get("sender_username") == own else (m.get("sender_username") or "")
        print("[%s] %s" % (m.get("type"), _fmt_line(m, sender)))
    print("%s（%s）共 %d 条" % (display, user, len(rows)))
    return 0


def cmd_export(args):
    db = _db()
    user, display, rows = _messages(db, args.chat, args.limit, 0, args.type)
    rows = list(reversed(rows))
    out = args.out or ("%s_%s.txt" % (display or user,
                                      __import__("time").strftime("%Y%m%d")))
    with io.open(out, "w", encoding="utf-8") as f:      # 永远 UTF-8，不跟控制台较劲
        for m in rows:
            f.write(_fmt_line(m) + "\n")
    print("已导出 %d 条 → %s" % (len(rows), os.path.abspath(out)))
    return 0


def cmd_send(args):
    if not (args.text or args.file or args.image):
        return _die("要发东西：`send 你好 --to 文件传输助手`，或 --file / --image")
    from wechatauto.guia import quick_send, quick_send_file, quick_send_image
    db = _db()
    _user, display = resolve_chat(db, args.to or "filehelper")
    if args.text:
        r = quick_send(args.text, display, verify=args.verify)
    elif args.file:
        r = quick_send_file(args.file, display, verify=args.verify)
    else:
        r = quick_send_image(args.image, display, verify=args.verify)
    print("%s：%s" % (getattr(r, "get", lambda *_: "")("status") or "?",
                      getattr(r, "get", lambda *_: "")("message") or ""))
    return 0 if r else 1


def cmd_images(args):
    db = _db()
    user, display = resolve_chat(db, args.chat)
    from wechatauto.media import MediaDownloader
    md = MediaDownloader(db, save_dir=args.out)
    if not md.detect_image_key():
        return _die("拿不到图片 AES 密钥：在微信里点开任意一张图片，让它驻留内存几秒"
                    "后重跑（`doctor` 会显示当前状态）")
    rows = db.get_image_rows(user, limit=args.limit) or []
    got = miss = bad = 0
    for r in rows:
        lid = r.get("local_id")
        if args.original:
            # 驱动真实界面去要原件：会点气泡、可能弹预览窗，走完一轮才回。
            out = md.download_image_original(user, lid, save_dir=args.out,
                                             chat_name=display)
        else:
            out = md.download_image(user, lid, save_dir=args.out, tier=args.tier)
        if out:
            got += 1
            print("  ✓ %s" % out)
        elif args.original:
            bad += 1
        else:
            miss += 1
            st = md.image_status(user, lid)
            print("  · local_id=%s 本机档位=%s reason=%s"
                  % (lid, st.get("tiers"), st.get("reason")))
    print("%s：%d 张已存 / %d 张本机没有 / %d 张没拿到"
          % (display or user, got, miss, bad))
    if miss and not args.original:
        print("提示：本机没有的那些，加 --original 会驱动微信界面去下载（会真的动你的微信窗口）")
    return 0


def cmd_listen(args):
    db = _db()
    from wechatauto.db import Listener
    lst = Listener(db, interval=args.interval)
    nick = {}

    def cb(msg, _l):
        # 回调给的是 username（`chat` 键），终端上打 wxid 没人看得懂，昵称查不到再退回
        who = msg.get("chat") or msg.get("username") or ""
        if who not in nick:
            try:
                nick[who] = db.get_nickname(who) or who
            except Exception:
                nick[who] = who
        print("[%s] %s" % (nick[who], _fmt_line(msg,
                                                msg.get("sender_username") or "")),
              flush=True)

    if args.all:
        lst.add_all(cb)
        print("监听所有会话（Ctrl+C 退出）…", flush=True)
    else:
        user, display = resolve_chat(db, args.chat)
        lst.add_listener(user, cb)
        print("监听 %s（Ctrl+C 退出）…" % display, flush=True)
    try:
        import time
        lst.start()
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass                      # Ctrl+C 落在 start 里也要走到下面的 stop
    finally:
        lst.stop()
    return 0


def cmd_moments(args):
    db = _db()
    from wechatauto import MomentDB
    mo = MomentDB(db)
    feeds = mo.get_my_moments(limit=args.limit) if args.me else \
        mo.get_moments(limit=args.limit)
    if args.json:
        print(json.dumps(feeds, ensure_ascii=False, indent=2))
        return 0
    for f in feeds:
        print("%s | %s | 图 %d 视频 %d 赞 %d 评 %d"
              % (f.get("nickname"), (f.get("text") or "")[:40],
                 len(f.get("images") or []), len(f.get("videos") or []),
                 len(f.get("likes") or []), len(f.get("comments") or [])))
    print("共 %d 条（本机缓存里有的）" % len(feeds))
    return 0


# ------------------------------------------------------------------ 装配
def build_parser():
    p = argparse.ArgumentParser(
        prog="python -m wechatauto",
        description="微信 4.x 本地库 + 界面自动化，一条命令版（原有 Python 接口不变）")
    p.add_argument("--version", "-V", "-v", action="version",
                   version="wechatauto %s" % _version())
    sub = p.add_subparsers(dest="cmd", metavar="子命令")

    def add(name, fn, help_text, **kw):
        s = sub.add_parser(name, help=help_text, description=help_text, **kw)
        s.set_defaults(func=fn)
        return s

    add("doctor", cmd_doctor, "一眼看清：账号 / 数据库密钥 / 图片密钥 / 控件树")

    s = add("sessions", cmd_sessions, "列出会话")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true")

    s = add("messages", cmd_messages, "看某个会话最近的消息")
    s.add_argument("chat", help="会话名 / 昵称 / 备注 / wxid / 群号都行")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--type", help="text/image/voice/video/file/link/system 或中文名")
    s.add_argument("--json", action="store_true")

    s = add("export", cmd_export, "把一个会话的消息导出成文本文件")
    s.add_argument("chat")
    s.add_argument("--limit", type=int, default=500)
    s.add_argument("--type")
    s.add_argument("--out", help="默认 <会话名>_<日期>.txt（UTF-8）")

    s = add("send", cmd_send, "发消息 / 文件 / 图片（会驱动微信窗口）")
    s.add_argument("text", nargs="?", help="要发的文本")
    s.add_argument("--to", help="发给谁（默认文件传输助手）")
    s.add_argument("--file")
    s.add_argument("--image")
    s.add_argument("--verify", action="store_true", help="发完回读数据库确认")

    s = add("images", cmd_images, "下载某个会话的图片")
    s.add_argument("chat")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--out", help="保存目录（默认库里的 DEFAULT_SAVE_PATH）")
    s.add_argument("--tier", choices=["original", "full", "best", "mid", "thumb"],
                   help="本机有哪一档给哪一档；不传 = 旧行为")
    s.add_argument("--original", action="store_true",
                   help="本机没有原件就驱动微信界面去下载（真的会动你的窗口）")

    s = add("listen", cmd_listen, "监听新消息并打印（Ctrl+C 退出）")
    s.add_argument("chat", nargs="?", help="--all 时可省略")
    s.add_argument("--all", action="store_true", help="监听所有会话")
    s.add_argument("--interval", type=float, default=1.0)

    s = add("moments", cmd_moments, "看朋友圈（本机缓存里有的）")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--me", action="store_true", help="只看自己发的")
    s.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    _utf8_stdout()
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        p.print_help()
        return 2
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\n已中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
