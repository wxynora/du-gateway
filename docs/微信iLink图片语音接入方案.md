# 微信 iLink 图片语音接入方案

结论：微信入口的图片、语音可以接，不需要自己从头逆向；直接参考现成 iLink/OpenClaw 协议实现即可。

## 目标

- 让微信入口除了文本外，还能接入：
  - 图片
  - 语音
- 并继续复用现有网关主链路：
  - 同一个 `tg_<TELEGRAM_PROACTIVE_TARGET_USER_ID>` 窗口
  - 同一份 `last_4`
  - 同一份 R2 历史
  - 同一份总结和动态记忆

## 已确认的信息

参考仓库：

- [hao-ji-xing/cc-weixin](https://github.com/hao-ji-xing/cc-weixin)
- 协议文档：`weixin-bot-api.md`

从这条现成协议线里，已经能确认：

- `sendmessage` 支持多种 `item_list.type`
  - `1` 文本
  - `2` 图片
  - `3` 语音
  - `4` 文件
  - `5` 视频
- 媒体不是直接发二进制
  - 先调 `/ilink/bot/getuploadurl`
  - 再传到微信 CDN
  - 再在 `sendmessage` 里带 CDN 信息
- 媒体链路涉及 `aes_key`
- 语音链路支持“语音本体 + 转文字相关字段”

所以结论不是“微信不支持”，而是“现有连接器还没把这层接上”。

## 和现有项目的对应关系

当前项目里，TG 的图片/语音能力不是主链路自己长出来的，而是 TG 入口先处理后再喂给网关：

- 图片：
  - TG 入口先下载图片
  - 转成 `image_url` 多模态
  - 再发给网关
- 语音：
  - TG/语音入口先拿到音频
  - 走 `services/stt.py`
  - 转文字后再发给网关

微信要补齐，方向也一样：

- 微信收图 -> 下载/解密 -> 转成多模态 `image_url`
- 微信收语音 -> 下载/解密 -> 走 STT -> 转文字进网关

## 建议实施顺序

### Phase 1：微信收图

目标：

- 微信用户发图片
- 连接器能拿到图片内容
- 转成和 TG 一样的 `image_url`
- 继续走现有聊天网关

落地方式：

- 在 `connectors/wechat_ilink/src/main.js` 里扩展入站 `item_list` 解析
- 识别 `type=2`
- 按 iLink 协议把图片下载并解密
- 转成 `data:<mime>;base64,...`
- 像 TG 一样组装：
  - `{"type":"text","text":"[图片]"}`
  - `{"type":"image_url","image_url":{"url":data_url}}`

### Phase 2：微信收语音转文字

目标：

- 微信用户发语音
- 连接器能拿到语音内容
- 调现有 `services/stt.py`
- 把识别出的文本继续发给网关

落地方式：

- 扩展入站 `item_list` 解析
- 识别 `type=3`
- 按 iLink 协议把语音下载并解密
- 调现有 STT 服务
- 把识别结果当作一条普通 user 文本发给网关

### Phase 3：微信回图片 / 回语音

目标：

- 网关输出图片或语音时，微信侧也能发回去

这一步比入站复杂，原因：

- 需要走 `getuploadurl`
- 需要上传 CDN
- 需要处理 `aes_key`
- 需要补微信侧媒体发送结构

所以建议放后面，不和前两步绑死。

## 先不做的范围

- 不先碰文件、视频
- 不先做群聊
- 不改网关主 pipeline
- 不为了微信去改记忆结构

## 预计会动的文件

- `connectors/wechat_ilink/src/main.js`

如需要抽公共能力，可能新增：

- `connectors/wechat_ilink/src/ilink_media.js`

原则：

- 只动微信连接器
- 不顺手改 TG 主逻辑
- 不动现有 Python 网关主链路

## 风险点

- iLink 媒体链路比文本复杂，关键在 CDN + AES
- 如果协议字段和现网版本有细小差异，要按实测修
- 语音 STT 成功率依赖音频格式和现有 Deepgram 配置

## 下一步建议

先做这两项最值：

1. 微信收图进网关
2. 微信收语音转文字进网关

这样就能先做到“微信输入能力接近 TG”，而不是一上来就把微信发媒体回包也全补完。
