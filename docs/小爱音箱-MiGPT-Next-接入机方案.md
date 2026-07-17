# 小爱音箱接入机

这套方案让机通过小爱音箱使用自己的声音说话，并通过小爱控制已经接入米家的家居设备。

## 1. 能实现什么

- 机主动说话：MiniMax 生成机音色的 mp3，小爱把它当作音乐播放。
- 控制米家设备：机说出自然语言命令，由小爱执行空调、红外家电等控制。
- 直接控制台灯：读取或设置开关、亮度和色温。

MiGPT Next 主要负责登录小米账号和调用音箱能力；机的对话、工具判断、语音合成与任务队列由网关服务负责。

## 2. 整体链路

### 机用自己的声音说话

```text
机决定通过小爱说话
-> 网关调用 MiniMax 生成 mp3
-> 网关保存 mp3，并生成短时有效的 HTTPS 地址
-> 网关把播放任务加入队列
-> MiGPT runner 领取任务
-> runner 调用 player_play_music
-> 小爱把 mp3 当作音乐播放
-> runner 把成功或失败结果回传给网关
```

播放实现只保留 `player_play_music`。mp3 地址写入音乐载荷里的 `stream.url`，不再并存第二套播放方式。

### 机控制米家设备

```text
机给出自然语言命令
-> 网关找到目标小爱音箱
-> 调用 execute-text-directive
-> 小爱理解命令
-> 米家或红外设备执行操作
```

例如：“打开卧室空调”“把风速调低一点”“关闭电视”。

### 直接控制台灯

台灯不必经过自然语言解析，可以直接读取或设置：

- 开关
- 亮度
- 色温

## 3. 准备条件

- 一台已绑定小米账号、能够正常联网的小爱音箱。
- 一台可长期运行 Docker 的 Linux 主机或 VPS。
- 一个带公网 HTTPS 的网关服务。
- MiniMax API Key 和机的音色 ID。
- MiGPT Next 所需的小米登录信息。
- 如需控制米家设备，再准备 `mijiaAPI` 的授权文件。

runner 通过小米云控制音箱，不要求和音箱处于同一局域网。推荐部署在长期在线的 VPS，常驻内存通常只需要几百 MB。

## 4. 小米账号授权

小米账号登录可以参考 MiGPT 要求的授权方式。取得可用的授权信息后保存并长期复用，不要在每次启动时重新登录。

米家控制使用 `mijiaAPI` 时，先完成一次授权并保存生成的 `auth.json`。后续直接读取该文件，不要把账号密码或授权文件提交到公开仓库。

## 5. 网关侧实现

### 5.1 生成语音

网关接到机的语音播放请求后：

1. 将要说的文字发给 MiniMax。
2. 指定机的音色、语速、音量、采样率和 mp3 格式。
3. 检查返回内容确实是有效音频。
4. 将音频保存为临时 mp3 文件。

建议把单条台词控制在适合自然朗读的长度。较长内容可以先按语义分段，再逐段生成和播放。

### 5.2 提供临时音频地址

小爱需要通过公网 HTTPS 拉取 mp3。音频地址应满足：

- 使用不可猜的随机标识。
- 设置较短的过期时间。
- 音频过期后自动清理。
- 支持小爱读取音频所需的普通 GET 请求。
- 同一条语音只允许有效播放一次，避免音箱反复拉取并循环播放。

不要把 mp3 只保存在单个 Web worker 的内存里。多 worker 部署时，应保存到所有 worker 都能读取的共享目录或对象存储。

### 5.3 播放任务队列

每条播放任务至少保存：

```json
{
  "id": "唯一任务 ID",
  "audio_url": "短时有效的 mp3 地址",
  "text": "本次播放的文字",
  "status": "pending",
  "created_at": "创建时间",
  "expires_at": "过期时间"
}
```

状态建议使用：

```text
pending -> claimed -> done
                    -> failed
```

runner 领取任务时应原子地把 `pending` 改为 `claimed`，避免多个 runner 重复播放同一条语音。长轮询超时只返回空结果，不把它记为失败。

### 5.4 runner 与网关通信

网关至少提供三类能力：

1. runner 长轮询领取下一条播放任务。
2. runner 回传任务成功或失败。
3. runner 定时上报在线状态和最近错误。

runner 和网关使用一串共享 Bearer Token 鉴权。领取接口只返回尚未过期的任务；长时间停留在 `claimed` 的任务可以按规则恢复为可领取状态。

## 6. MiGPT runner 实现

runner 启动后完成以下工作：

1. 使用小米授权信息初始化 MiGPT Next。
2. 选择目标小爱音箱。
3. 定时向网关上报在线状态。
4. 长轮询领取播放任务。
5. 使用 `player_play_music` 播放 mp3。
6. 校验音箱实际接受的 `audio_id`。
7. 回传 `done` 或 `failed`。

关键播放逻辑如下：

```js
function buildMusicPayload(audioUrl, audioId) {
  return {
    startaudioid: audioId,
    music: JSON.stringify({
      payload: {
        audio_type: "",
        audio_items: [
          {
            item_id: {
              audio_id: audioId,
              cp: {
                album_id: "-1",
                episode_index: 0,
                id: "355454500",
                name: "xiaowei"
              }
            },
            stream: { url: audioUrl }
          }
        ],
        list_params: {
          listId: "-1",
          loadmore_offset: 0,
          origin: "xiaowei",
          type: "MUSIC"
        }
      },
      play_behavior: "REPLACE_ALL"
    })
  };
}

const payload = buildMusicPayload(task.audio_url, createAudioId(task.audio_url));
const result = await MiNA.callUbus(
  "mediaplayer",
  "player_play_music",
  payload
);
```

`audio_id` 不要写成固定值。可以根据每个音频地址生成新的稳定 ID，避免和小米曲库中的真实歌曲发生碰撞。播放命令返回成功后，再读取一次播放状态；如果实际 `audio_id` 与本次任务不一致，应立即停止播放并把任务标为失败。

runner 只实现 `player_play_music` 这一条经过实测的播放链路，不再添加其他播放兜底。

## 7. 米家设备控制

### 7.1 自然语言控制

网关使用 `mijiaAPI` 登录后：

1. 同时读取账号自有设备和共享设备。
2. 合并并去重设备列表。
3. 按完整设备名或 DID 找到目标小爱音箱。
4. 调用音箱的 `execute-text-directive`，把命令交给小爱执行。

调用的是小爱音箱的文本指令能力，常见 MIoT 动作为：

```text
siid = 5
aiid = 4
```

参数中放入完整自然语言命令。最终控制逻辑仍由小爱和米家完成，因此也能覆盖红外遥控设备。

### 7.2 音箱音量

音箱音量最好单独解析并直接写入 `volume`，不要再绕一遍自然语言。这样“音量调到 30%”之类的命令更稳定。

### 7.3 台灯结构化控制

台灯使用 DID 直接访问属性：

- `on`：开关
- `brightness`：亮度
- `color-temperature`：色温

读取时返回当前值；设置时校验数值范围，再调用对应属性写入。设备不在线或属性不支持时，应把真实错误返回给机。

## 8. Docker 部署

runner 可以使用轻量 Node.js 镜像：

```yaml
services:
  xiaoai-runner:
    build: .
    restart: unless-stopped
    env_file: .env
    mem_limit: 256m
    environment:
      NODE_OPTIONS: --max-old-space-size=128
```

`.env` 至少包含：

```dotenv
XIAOMI_USER_ID=<小米账号>
XIAOMI_PASSWORD=<密码或留空>
XIAOMI_PASS_TOKEN=<passToken 或留空>
XIAOAI_DID=<目标音箱名称或 DID>
XIAOAI_SPEAKER=<目标音箱名称>

GATEWAY_URL=https://gateway.example.com
GATEWAY_TOKEN=<与网关一致的随机密钥>

ACTION_POLL_MS=5000
ACTION_CLAIM_WAIT_SECONDS=12
PLAY_STRATEGY=music
```

启动并查看日志：

```bash
docker compose up -d --build
docker compose logs -f
```

## 9. 验收顺序

按下面顺序检查，比较容易定位问题：

1. 小爱音箱在米家中在线，能正常播放音乐。
2. runner 能登录小米账号并找到目标音箱。
3. runner 能访问网关 HTTPS 和任务领取接口。
4. 浏览器能正常读取一条测试 mp3。
5. runner 能领取测试任务并调用 `player_play_music`。
6. 小爱实际播放的是测试 mp3，而不是小米曲库里的其他音乐。
7. MiniMax 能生成机音色的 mp3，并完成完整播放链路。
8. `execute-text-directive` 能控制一个米家或红外设备。
9. 台灯开关、亮度和色温能分别读取与设置。

## 10. 常见问题

### runner 显示在线，但小爱没有声音

- 确认使用的是 `player_play_music`。
- 检查 mp3 地址能否从公网直接访问。
- 检查 HTTPS 证书是否有效。
- 查看播放状态中的 `audio_id` 是否与本次任务一致。
- 确认音箱音量不是 0，也没有处于勿扰状态。

### 播放成了不相干的歌曲

- 不要复用固定 `audio_id`。
- 每个 mp3 地址生成新的 `audio_id`。
- 播放后校验实际 `audio_id`，不一致就立刻停止。

### 同一句话反复播放

- 音频地址应短时有效并限制重复读取。
- 检查任务领取是否具备原子状态更新。
- 检查失败任务是否被无限重新放回队列。

### 能播放语音，但不能控制家居

- 语音播放和家居控制是两条独立链路。
- 检查 `mijiaAPI` 授权文件是否有效。
- 同时检查自有设备和共享设备。
- 确认找到的是目标小爱音箱，再调用 `execute-text-directive`。

## 11. 安全边界

- 小米密码、passToken、MiniMax Key、网关 Token 和 `auth.json` 只保存在私密环境变量或受限文件中。
- 播放任务接口必须鉴权。
- mp3 地址使用随机标识和短 TTL，不提供永久公开目录。
- 日志不要输出完整 Token、密码、授权文件内容或真实设备 ID。
- 对外分享配置时统一使用占位符。
