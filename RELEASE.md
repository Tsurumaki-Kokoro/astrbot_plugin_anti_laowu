# v0.1.0 发布准备

## GitHub Release 文案

标题：`v0.1.0 · 可配置防老吴器`

两台机器人在群里老吴起来？给它们加个冷却，让人类说两句。

本版本提供按账号和群独立的冷却、连续互动暂停、可选放行概率与指令豁免。引用、@和关键词不能绕过限流，重启后保留状态。

安装后请先填写目标QQ号：默认名单为空，不会自动识别或限制机器人。默认规则为180秒最多放行一次，连续2次后暂停300秒。可在插件配置中调整。

兼容范围：AstrBot >=4.29.1，OneBot/aiocqhttp群聊。无额外第三方依赖。

注意：放行次数不等于成功送达数；拦截会停止消息的后续插件链。需要保留点歌等指令时配置豁免白名单；严格限制时清空白名单。

## 发布核对

- [x] 默认目标列表为空，代码不包含实际目标QQ号。
- [x] metadata名称、作者、版本、仓库和平台信息齐全。
- [x] logo为用户提供的256×256 PNG。
- [x] 11项自动测试通过；真实AstrBot环境离线检查见VALIDATION.md。
- [x] 仓库保留原有GPL-3.0许可证。
- [ ] 测试群实测：@、引用、关键词循环、多人插话与指令豁免。
- [ ] 确认GitHub Release草稿附件与SHA256。
- [ ] 发布Release，然后登录AstrBot Cloud提交审核。

## 构建

```sh
python -m unittest discover -s tests -v
python scripts/build_release.py
```

产物位于dist目录。构建只收录显式列出的运行文件、logo、许可证、README及更新记录，不包含.git、日志、数据库、真实配置或测试缓存。构建时会检查ZIP小于16MiB，并输出SHA256。

## 插件市场提交资料

发布入口：https://cloud.astrbot.app/publish

| 字段 | 内容 |
|---|---|
| 仓库 | https://github.com/Tsurumaki-Kokoro/astrbot_plugin_anti_laowu |
| 展示名称 | 可配置防老吴器 |
| 标识符 | astrbot_plugin_anti_laowu |
| 作者 | Tsurumaki-Kokoro |
| 版本 | 0.1.0 |
| 简介 | 防止机器人之间高强度互聊，支持按账号与群配置冷却和连续互动暂停。 |
| 平台 | aiocqhttp |
| 最低AstrBot版本 | 4.29.1 |
| 标签 | 群聊、限流、机器人互动 |

官方说明要求注册AstrBot Cloud账号；仓库合并或GitHub Release本身不代表已进入市场。提交时核对自动读取的metadata，并按页面填写实际必填字段。

官方发布说明：https://docs.astrbot.app/dev/star/plugin-publish.html
