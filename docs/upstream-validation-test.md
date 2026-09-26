# wechatauto-replica 上游能力验收测试

## 目标

验证上游 wechatauto-replica 核心能力，在集成 Qlawork 前确认底层能力可用。

## 测试范围

- [ ] 微信账号初始化
- [ ] WCDB 解密与读取
- [ ] 联系人/session读取
- [ ] 消息读取
- [ ] Listener增量监听
- [ ] 文本发送
- [ ] 文件发送
- [ ] 图片发送
- [ ] 回复/@能力
- [ ] 媒体下载

## 重点关注

发送链路不经过企业封装，直接验证原生 GUI 自动化能力。

验证入口：

```python
quick_send("测试消息", "文件传输助手", verify=True)
```

## 通过标准

所有基础能力通过后，再进入 Qlawork Provider 集成。