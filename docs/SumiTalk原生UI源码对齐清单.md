# SumiTalk 原生 UI 源码对齐清单

## 目标

保留 `du-gateway/miniapp` 当前 UI 的视觉和交互，不再按印象重新设计；在 `sumitalk-android-native` 中把同一套界面翻译成可维护的 Jetpack Compose 实现。

原版 TSX、CSS、Tailwind 配置和资源文件是唯一设计依据。截图只负责验证翻译结果，不能代替读取源码。

## 边界

- 不推倒原生仓库已经完成的聊天运行时、SQLite、恢复、语音、媒体、悬浮球、通知和无障碍实现。
- 不把 React 组件或 WebView 放回最终原生 APK。
- 不用 Material 3 默认视觉替代原版；Material 组件可以作为行为基础，但可见颜色、尺寸、形状和排版必须服从 MiniApp。
- 不用脚本直接覆盖已有 Kotlin 页面。脚本输出报告、机器清单和 token 骨架，原生仓库按组件审阅后应用。
- 不在 UI 对齐阶段顺手改后端协议或业务规则。

## 本地脚本

在 `du-gateway` 根目录运行：

```bash
npm --prefix miniapp run audit:native-ui-parity -- \
  --native-root ../sumitalk-android-native \
  --output /tmp/sumitalk-native-ui-parity.md \
  --json-output /tmp/sumitalk-native-ui-parity.json \
  --kotlin-output /tmp/MiniAppSourceTokens.kt
```

默认原生仓库就是同级目录 `../sumitalk-android-native`，因此也可以省略 `--native-root`。

脚本会：

- 用 TypeScript AST 读取 TS/TSX 的静态 `className`、内联 `style`、组件和资源引用。
- 用 PostCSS 读取 `styles.css` 的 CSS 变量、属性和 keyframes。
- 读取 `tailwind.config.js` 的颜色、圆角和阴影 token。
- 扫描原生 Kotlin/Java 中的硬编码颜色、`dp`、`sp`、圆角和阴影，并按文件生成热点排名。
- 比较 MiniApp 与原生仓库的精确十六进制颜色交集和两侧独有颜色。
- 生成可选的 Kotlin token 骨架，但不会修改原生仓库。

脚本不会自动判断动态运行结果，也不会替代人工处理字体度量、复杂渐变、毛玻璃、多层阴影、伪元素、Canvas、任意 HTML 和输入法行为。

## 对齐顺序

### 0. 固定基线

- [ ] 保留原生仓库当前功能代码，不从空项目重开。
- [ ] 记录当前提交和工作区状态，分清已有修改与本轮样式修改。
- [ ] 运行 `:app:assembleDebug`、`:app:testDebugUnitTest`、`:app:lintDebug`。
- [ ] 在固定设备、系统字体大小 100%、显示大小默认值下保存当前原生截图。
- [ ] 保存同设备尺寸下 MiniApp 的参考截图，命名包含页面、状态、宽高和日期。

### 1. 设计 token

源码：

- `miniapp/tailwind.config.js`
- `miniapp/src/styles.css`
- `miniapp/src/ui/chatAppearance.ts`
- `miniapp/src/ui/ChatPresentation.tsx`

原生目标：

- `app/src/main/java/com/sumitalk/nativeapp/ui/theme/SumiTalkTheme.kt`
- 新增或收束一个原版 token 文件，供页面共享。

检查：

- [ ] `cream.bg/card/border/text/muted/accent/blue/pink/green/danger` 全部进入原生 token。
- [ ] `xl2=18px`、`xl3=28px` 和页面用到的任意圆角有明确 Compose 对应值。
- [ ] `soft`、`soft2`、`--neo-shadow-*`、`--neo-inset` 被拆成可审阅的 Compose 阴影层，不用单个 elevation 猜效果。
- [ ] 原版字体文件进入 Android 资源并显式映射字重；不依赖系统默认字体碰运气。
- [ ] 页面不再直接接受当前蓝色 Material 默认配色。
- [ ] 深色模式只在原版有对应设计时启用，不能由系统主题自动把页面改成另一套风格。

### 2. P0 公共组件

#### App 外壳与底栏

源码：`AppShell.tsx`、`BottomNav.tsx`

原生：`SumiTalkApp.kt`、`SumiTalkHomeHost.kt`、`BottomCapsuleNav.kt`

- [ ] 状态栏、导航栏、键盘和安全区行为一致。
- [ ] 页面背景、底栏高度、宽度、图标尺寸、选中态、阴影和透明度一致。
- [ ] 页面切换不改变布局尺寸，不出现 Compose 默认水波纹或默认强调色。

#### 会话首页

源码：`ChatsHome.tsx`、`AppShell.tsx`

原生：`ConversationHomeScreen.kt`

- [ ] 标题、头像、摘要、时间、未读/状态、行高和分隔关系一致。
- [ ] 空态、长摘要、超长名称和自定义背景状态一致。

#### 聊天页

源码：`MainChatScreen.tsx`、`ChatPresentation.tsx`、`sumitalkSystemCards.tsx`

原生：`ChatScreen.kt`、`ChatSystemCards.kt`、`ChatAppearance.kt`

- [ ] 顶部栏、头像、在线/输入中状态、Real 状态两行布局一致。
- [ ] 用户、渡、笨笨、系统提示、撤回提示分别使用原版气泡结构。
- [ ] 连续消息合并、头像显隐、时间戳、尾巴、边距和最大宽度一致。
- [ ] Markdown 标题、列表、引用、代码、表格和链接有原生对应实现。
- [ ] Cot、工具调用、工具轮中间对话和最终回复保持原有显示边界。
- [ ] 流式追加不跳动、不重复、不把最终内容重新插成第二条消息。
- [ ] 输入栏、附件、录音、发送/停止按钮、键盘抬升和底部安全区一致。
- [ ] 搜索、编辑重发、引用、长按菜单、图片预览和弹窗状态一致。

### 3. P1 设置体系

源码：

- `SettingsRows.tsx`
- `PersonalizationScreen.tsx`
- `PromptManagerScreen.tsx`
- `DiagnosticsScreen.tsx`
- `DeviceManagerModal.tsx`
- `tabs/SettingsUpstream.tsx`
- `tabs/ChatStorageManagementScreen.tsx`

原生目标：

- `SettingsHomeScreen.kt`
- `detail/settings/*Screen.kt`
- `SettingsDetailComponents.kt`
- `PersonalizationComponents.kt`

- [ ] 先统一列表行、分组标题、开关、输入框、选择器、弹窗和顶部栏，再修具体页面。
- [ ] 所有页面复用共享组件，不在每个 Screen 复制一套相似颜色和间距。
- [ ] 加载、保存中、失败、禁用、空值、版本冲突和退出登录状态齐全。

### 4. P2 陪伴与工具页面

- [ ] `StayWithDuScreen.tsx` 对齐 `CompanionHomeScreen.kt`。
- [ ] Pixel Home、渡的一天、共读、一起听、交换日记、秘密抽屉、梦境和观看清单逐页建立源码映射。
- [ ] 复杂游戏、Canvas、音频和 HTML 页面单列，不用通用卡片风格强行抹平原设计。
- [ ] 每个页面先迁共享视觉，再处理特有动画和交互。

## 每个页面的执行模板

- [ ] 在报告中找到该 TSX 文件和对应 Kotlin 文件。
- [ ] 阅读 JSX 层级、所有静态/条件 `className`、内联 `style` 和资源引用。
- [ ] 列出正常、加载、空、失败、禁用、弹窗、键盘、长内容等状态。
- [ ] 先替换成共享 token 和组件，再保留页面特有值。
- [ ] 原生构建通过。
- [ ] 在相同宽高、字体比例和内容数据下截取新旧页面。
- [ ] 检查布局、换行、颜色、透明度、阴影、圆角、图标、触控区域和动画。
- [ ] 把仍需保留的硬编码值写成有来源的局部常量，而不是散落数字。
- [ ] 更新报告；热点下降且未引入新的无来源颜色后再勾完成。

## 验收标准

- [ ] 页面结构和信息密度与 MiniApp 一致，不新增装饰卡片、营销式留白或 Material 默认外观。
- [ ] 主要几何位置误差不超过 2dp；固定格式控件尺寸不随内容跳动。
- [ ] 字体家族、字重、字号、行高和长文本换行经过真机核对。
- [ ] 原版多层阴影、透明层和背景效果按层实现，不只比较一个颜色值。
- [ ] 360dp、390dp 和一台较宽设备均无重叠、截断或横向溢出。
- [ ] 系统字体 100% 为像素对齐基线；较大字体下仍可读且不遮挡。
- [ ] 深色背景、自定义聊天背景、无背景三种聊天外观分别验收。
- [ ] 流式、断网恢复、切后台恢复、旋转/重建、杀进程恢复不破坏消息顺序。
- [ ] `assembleDebug`、单元测试、`lintDebug` 和真机安装均通过。

## 当前状态

- 已完成：在 `du-gateway` 增加只读 UI 对齐审计脚本与本清单；脚本可从 MiniApp 源码生成 Markdown、JSON 和 Kotlin token 骨架。
- 未完成：没有修改 `sumitalk-android-native`，没有把生成 token 应用到 Compose，也没有进行新一轮截图对齐。
- 下次从这里继续：在原生仓库运行脚本，先处理 `SumiTalkTheme.kt`、`BottomCapsuleNav.kt`、`ConversationHomeScreen.kt` 和 `ChatScreen.kt`。
- 不要碰：原生仓库现有聊天运行时、本地数据库、语音、恢复和系统服务逻辑；本轮只收视觉层及其必要的 UI 状态映射。
