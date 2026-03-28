--[[--
@module koplugin.du_co_read
--]]

local Dispatcher = require("dispatcher") -- luacheck:ignore
local InfoMessage = require("ui/widget/infomessage")
local MultiInputDialog = require("ui/widget/multiinputdialog")
local TextViewer = require("ui/widget/textviewer")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local _ = require("gettext")

local JSON = require("json")
local logger = require("logger")

local util = require("util")
local Device = require("device")
local NetworkMgr = require("ui/network/manager")

local http = require("socket.http")
local ltn12 = require("ltn12")
local socket = require("socket")
local socketutil = require("socketutil")

local CoRead = WidgetContainer:extend{
    name = "du_co_read",
    is_doc_only = false,
}

-- 与 Wallabag / HighlightSync 等一致：走全局 G_reader_settings，避免单独 LuaSettings 文件在部分安卓上 flush 崩进程。
local SETTINGS_KEY = "du_co_read"

CoRead.default_settings = {
    -- 网关基址，例如 http://127.0.0.1:5000
    gateway_base_url = "http://127.0.0.1:5000",
    -- 目前仓库已实现：/v1/chat/completions（插件默认走它可先跑通）
    gateway_chat_path = "/v1/chat/completions",
    -- 文档约定：/api/co-read/session（后续你实现后可切换到这里）
    gateway_co_read_path = "/api/co-read/session",
    -- 保存划词注释时静默 POST（与网关 routes/koreader_api 一致）
    gateway_koreader_path = "/api/koreader",
    -- 是否与 KOReader AnnotationsModified（nb_notes_added=1）同步到网关
    koreader_hook_enabled = true,
    -- chat | co_read_session
    mode = "co_read_session",
    -- 用于区分窗口记忆；建议填一个稳定值（例如 koreader）
    window_id = "tg_8260066512",
    -- 可选：当你的网关需要额外鉴权时填 Bearer Token
    bearer_token = "",
    -- 单次上送片段最大字符数（超长会截断）
    snippet_max_chars = 4000,
    -- 为 true 时：点「发给渡一起看」不再弹共读输入框，附言固定读系统剪贴板（系统输入法里先复制）。
    co_read_note_from_clipboard = false,
}

function CoRead:loadRuntimeSettings()
    local raw = {}
    if G_reader_settings and G_reader_settings.readSetting then
        raw = G_reader_settings:readSetting(SETTINGS_KEY, {}) or {}
    end
    if type(raw) ~= "table" then
        raw = {}
    end
    local merged = {}
    for k, v in pairs(self.default_settings) do
        merged[k] = raw[k] ~= nil and raw[k] or v
    end
    self.runtime_settings = merged
end

function CoRead:saveRuntimeSettings()
    if not (G_reader_settings and G_reader_settings.saveSetting) then
        return
    end
    G_reader_settings:saveSetting(SETTINGS_KEY, self.runtime_settings)
end

function CoRead:init()
    self.ui.menu:registerToMainMenu(self)
    self:loadRuntimeSettings()
    self._highlight_button_added = false
end

function CoRead:addToMainMenu(menu_items)
    menu_items.du_co_read = {
        text = _("共读：发给渡（KOReader）"),
        sub_item_table = {
            {
                text = _("设置网关基址"),
                callback = function()
                    self:showSettingDialog(
                        _("网关基址（gateway_base_url）"),
                        self.runtime_settings.gateway_base_url or self.default_settings.gateway_base_url,
                        function(v)
                            self.runtime_settings.gateway_base_url = (v or ""):gsub("/$", "")
                            self:saveRuntimeSettings()
                        end
                    )
                end,
            },
            {
                text = _("设置窗口ID"),
                callback = function()
                    self:showSettingDialog(
                        _("窗口ID（window_id）"),
                        self.runtime_settings.window_id or self.default_settings.window_id,
                        function(v)
                            self.runtime_settings.window_id = (v or ""):gsub("%s+", "")
                            self:saveRuntimeSettings()
                        end
                    )
                end,
            },
            {
                text = _("模式：chat（走 /v1/chat/completions）"),
                checked_func = function()
                    return self.runtime_settings.mode == "chat"
                end,
                callback = function()
                    self.runtime_settings.mode = "chat"
                    self:saveRuntimeSettings()
                end,
            },
            {
                text = _("模式：co_read_session（走 /api/co-read/session）"),
                checked_func = function()
                    return self.runtime_settings.mode == "co_read_session"
                end,
                callback = function()
                    self.runtime_settings.mode = "co_read_session"
                    self:saveRuntimeSettings()
                end,
            },
            {
                text = _("设置 Bearer Token（可选）"),
                callback = function()
                    self:showSettingDialog(
                        _("Bearer Token（bearer_token）"),
                        self.runtime_settings.bearer_token or "",
                        function(v)
                            self.runtime_settings.bearer_token = v or ""
                            self:saveRuntimeSettings()
                        end
                    )
                end,
            },
            {
                text = _("共读附言：改用剪贴板（不弹编辑框）"),
                checked_func = function()
                    return self.runtime_settings.co_read_note_from_clipboard == true
                end,
                callback = function()
                    self.runtime_settings.co_read_note_from_clipboard =
                        not self.runtime_settings.co_read_note_from_clipboard
                    self:saveRuntimeSettings()
                end,
            },
            {
                text = _("划词保存注释时同步到网关（静默）"),
                checked_func = function()
                    return self.runtime_settings.koreader_hook_enabled ~= false
                end,
                callback = function()
                    self.runtime_settings.koreader_hook_enabled =
                        not (self.runtime_settings.koreader_hook_enabled ~= false)
                    self:saveRuntimeSettings()
                end,
            },
        },
    }
end

function CoRead:showSettingDialog(title, current_value, setter)
    -- 单字段用 MultiInputDialog（与内置插件一致），比 InputDialog 在安卓 MIUI 上稳得多。
    local dlg
    dlg = MultiInputDialog:new{
        title = title,
        fields = {
            {
                text = tostring(current_value or ""),
                hint = _("输入后点保存"),
            },
        },
        buttons = {
            {
                {
                    text = _("Cancel"),
                    id = "close",
                    callback = function()
                        UIManager:close(dlg)
                    end,
                },
                {
                    text = _("Save"),
                    is_enter_default = true,
                    callback = function()
                        local fields = dlg:getFields()
                        local v = fields and fields[1] or ""
                        local ok_save, err_save = pcall(function()
                            setter(v)
                        end)
                        if not ok_save then
                            logger.err("du_co_read save err: " .. tostring(err_save))
                            UIManager:show(InfoMessage:new{
                                text = _("保存失败，请重试。"),
                                timeout = 4,
                            })
                            return
                        end
                        UIManager:close(dlg)
                    end,
                },
            },
        },
    }
    UIManager:show(dlg)
    dlg:onShowKeyboard()
end

function CoRead:onReaderReady()
    -- 整段包 pcall：避免个别版本上注册高亮按钮失败导致日志里难查的静默问题。
    local ok_reg, err_reg = pcall(function()
        if self._highlight_button_added then
            return
        end
        if not (self.ui and self.ui.highlight and self.ui.highlight.addToHighlightDialog) then
            return
        end

        -- 只注册一个高亮按钮：部分设备/旧版上连续 addToHighlightDialog 两次曾导致异常。
        -- 附言走剪贴板：在菜单里打开「共读附言：改用剪贴板」。
        self.ui.highlight:addToHighlightDialog("du_co_read_send", function(reader_highlight)
            return {
                text = _("发给渡一起看"),
                enabled = true,
                callback = function()
                    -- 必须用 self:xxx，且方法名不要以 on 开头，避免被 PluginLoader 包成沙箱后 dot 调用异常。
                    self:sendSelectedToDu(reader_highlight)
                end,
            }
        end)

        self._highlight_button_added = true
    end)
    if not ok_reg then
        logger.err("du_co_read onReaderReady: " .. tostring(err_reg))
    end
end

local function cleanupForPayload(s)
    s = tostring(s or "")
    -- 替换掉明显的多余空白，避免 token 浪费
    s = s:gsub("%s+", " ")
    s = s:sub(1, 50000)
    return s
end

-- 安卓等平台上 Device.input 可读系统剪贴板，用于「附言用系统输入法写好再复制」。
local function readClipboardAsNote()
    local input = Device and Device.input
    if not input or type(input.hasClipboardText) ~= "function" or type(input.getClipboardText) ~= "function" then
        return ""
    end
    local ok_h, has = pcall(function()
        return input.hasClipboardText()
    end)
    if not ok_h or not has then
        return ""
    end
    local ok_t, text = pcall(function()
        return input.getClipboardText()
    end)
    if not ok_t or not text or text == "" then
        return ""
    end
    return cleanupForPayload(text)
end

-- 关掉高亮菜单后再执行 fn（勿在 fn 里再读 reader_highlight.selected_text）。
function CoRead:afterHighlightMenuClosed(reader_highlight, fn)
    UIManager:scheduleIn(0, function()
        pcall(function()
            if reader_highlight and reader_highlight.onClose then
                reader_highlight:onClose(false)
            end
        end)
        UIManager:scheduleIn(0.25, fn)
    end)
end

function CoRead:guessBookTitle(reader_highlight)
    local ui = reader_highlight and reader_highlight.ui
    if ui and ui.doc_props and ui.doc_props.title and (ui.doc_props.title ~= "") then
        return tostring(ui.doc_props.title)
    end
    local doc = ui and ui.document
    if doc and doc.file then
        local file = tostring(doc.file)
        local name = file:match("([^/\\]+)$") or file
        return name
    end
    return ""
end

function CoRead:guessChapterLabel(reader_highlight)
    local ui = reader_highlight and reader_highlight.ui
    local selected = reader_highlight and reader_highlight.selected_text
    local page = selected and selected.pos0 and selected.pos0.page
    if ui and ui.toc and ui.toc.getTocTitleByPage and page then
        local v = ui.toc:getTocTitleByPage(page)
        if v then return tostring(v) end
    end
    return ""
end

-- 与 guessBookTitle 同源：从当前 ReaderUI 取书名（无 reader_highlight 时用 self.ui）
function CoRead:bookTitleFromUi(ui)
    ui = ui or self.ui
    if ui and ui.doc_props and ui.doc_props.title and ui.doc_props.title ~= "" then
        return tostring(ui.doc_props.title)
    end
    local doc = ui and ui.document
    if doc and doc.file then
        local file = tostring(doc.file)
        return file:match("([^/\\]+)$") or file
    end
    return ""
end

function CoRead:bookAuthorFromUi(ui)
    ui = ui or self.ui
    local props = ui and ui.doc_props
    if not props then
        return ""
    end
    local a = props.authors or props.author
    if type(a) == "table" then
        a = table.concat(a, ", ")
    end
    return cleanupForPayload(tostring(a or ""))
end

-- 阅读进度 0–100；失败则 0（与 KOReader getCurrentPage / getPageCount 惯例一致）
function CoRead:readingProgressPercent(ui)
    ui = ui or self.ui
    local doc = ui and ui.document
    if not doc or not doc.getPageCount then
        return 0
    end
    local total = doc:getPageCount()
    if not total or total < 1 then
        return 0
    end
    local cur
    if ui.getCurrentPage then
        cur = ui:getCurrentPage()
    end
    if not cur or cur < 1 then
        return 0
    end
    return math.min(100, math.max(0, math.floor((cur / total) * 100 + 0.5)))
end

function CoRead:chapterForAnnotation(ui, ann)
    if ann and ann.chapter and tostring(ann.chapter) ~= "" then
        return tostring(ann.chapter)
    end
    local page = ann and ann.pageno
    if ui and page and ui.toc and ui.toc.getTocTitleByPage then
        local v = ui.toc:getTocTitleByPage(page)
        if v then
            return tostring(v)
        end
    end
    return ""
end

-- KOReader 事件名 AnnotationsModified；须保留 on 前缀供框架派发。
-- 仅在「高亮首次保存为带注释」时 readerbookmark 会带 nb_notes_added=1（见上游 setBookmarkNote）。
function CoRead:onAnnotationsModified(items)
    if self.runtime_settings.koreader_hook_enabled == false then
        return
    end
    if type(items) ~= "table" or tonumber(items.nb_notes_added) ~= 1 then
        return
    end
    local ann = items[1]
    if not ann or not ann.drawer then
        return
    end
    local hl = cleanupForPayload(ann.text or "")
    if hl == "" then
        return
    end
    local note_raw = ann.note
    local note = (note_raw and cleanupForPayload(note_raw)) or ""

    local ui = self.ui
    local payload = {
        book = {
            title = self:bookTitleFromUi(ui),
            author = self:bookAuthorFromUi(ui),
            chapter = self:chapterForAnnotation(ui, ann),
            progress = self:readingProgressPercent(ui),
        },
        highlight = hl,
        note = note,
        timestamp = os.time(),
    }

    UIManager:scheduleIn(0, function()
        self:postKoreaderHighlightSilent(payload)
    end)
end

-- 异步、失败仅 logger，不弹窗（与 doSendToDu 共用 postJson / 网关配置）
function CoRead:postKoreaderHighlightSilent(payload)
    UIManager:scheduleIn(0.08, function()
        local settings = self.runtime_settings or {}
        local base = (settings.gateway_base_url or ""):gsub("/$", "")
        if base == "" then
            return
        end
        local path = settings.gateway_koreader_path or "/api/koreader"
        local url = base .. path
        local wid = settings.window_id or ""
        local bearer = settings.bearer_token or ""

        local ok_enc, encoded = pcall(JSON.encode, payload)
        if not ok_enc or type(encoded) ~= "string" or encoded == "" then
            logger.err("du_co_read koreader JSON.encode 失败: " .. tostring(encoded))
            return
        end

        local headers = {
            ["Content-Type"] = "application/json; charset=utf-8",
            ["content-length"] = tostring(#encoded),
        }
        if wid ~= "" then
            headers["X-Window-Id"] = wid
        end
        if bearer ~= "" then
            headers["Authorization"] = "Bearer " .. bearer
        end

        local ok, result = self:postJson(url, encoded, headers)
        if not ok then
            logger.warn("du_co_read koreader POST 失败: " .. tostring(result and result.kind or result))
        end
    end)
end

function CoRead:buildCoReadUserMessage(book_title, chapter_label, snippet, user_note)
    local msg = "[CO-READ]\n"
    msg = msg .. "Book: " .. tostring(book_title) .. "\n"
    if chapter_label and chapter_label ~= "" then
        msg = msg .. "Chapter: " .. tostring(chapter_label) .. "\n"
    end
    msg = msg .. "Snippet:\n" .. tostring(snippet) .. "\n"
    if user_note and user_note ~= "" then
        msg = msg .. "UserNote:\n" .. tostring(user_note) .. "\n"
    end
    msg = msg .. "[/CO-READ]\n"
    msg = msg .. "回应这段共读内容即可。"
    return msg
end

function CoRead:postJson(url, body, headers)
    -- body 为已序列化的 JSON 字符串（便于统一设置 Content-Length，并避免编码异常直接把 UI 线程打崩）
    local response_chunks = {}
    local request = {
        url = url,
        method = "POST",
        headers = headers or {},
        source = ltn12.source.string(body),
        sink = ltn12.sink.table(response_chunks),
    }

    -- 单次阻塞与整次请求上限都要留足：网关会再调 LLM，常超过 30s；原先 (10,30) 会误判成「网络错误」。
    socketutil:set_timeout(45, 180)
    local ok_http, code, resp_headers, status = pcall(function()
        return socket.skip(1, http.request(request))
    end)
    socketutil:reset_timeout()

    if not ok_http then
        return false, { kind = "http_exception", detail = tostring(code) }
    end

    if resp_headers == nil then
        local err_hint = tostring(code or "")
        if err_hint == "timeout" or err_hint:find("timeout", 1, true) then
            err_hint = err_hint .. " (" .. _("若网关已通，多为模型响应超过等待上限") .. ")"
        end
        return false, {
            kind = "network_error",
            code = code,
            status = status,
            detail = err_hint,
            body = nil,
        }
    end

    local resp_text = table.concat(response_chunks)
    if not resp_text or resp_text == "" then
        if code and tonumber(code) and tonumber(code) >= 400 then
            return false, { kind = "http_error", status_code = code, resp = {} }
        end
        return true, { status_code = code, resp = {} }
    end

    local ok, resp_json = pcall(JSON.decode, resp_text)
    if ok then
        if code and tonumber(code) and tonumber(code) >= 400 then
            return false, { kind = "http_error", status_code = code, resp = resp_json }
        end
        return true, { status_code = code, resp = resp_json }
    end

    if code and tonumber(code) and tonumber(code) >= 400 then
        return false, { kind = "http_error", status_code = code, resp = { _raw = resp_text } }
    end
    return true, { status_code = code, resp = { _raw = resp_text } }
end

function CoRead:extractAssistantContent(chat_resp)
    local choices = chat_resp and chat_resp.choices
    if not (choices and choices[1] and choices[1].message) then
        return ""
    end
    local content = choices[1].message.content or ""
    return tostring(content)
end

-- 方法名勿用 on 前缀：KOReader 会把 on* 包成 HandlerSandbox，内部用 CoRead.onXxx(self) 易与部分版本不兼容。
function CoRead:sendSelectedToDu(reader_highlight)
    if not (reader_highlight and reader_highlight.selected_text) then
        UIManager:show(InfoMessage:new{ text = _("未获取到选中内容。") })
        return
    end

    -- 必须先拷贝数据：后面会关掉高亮菜单，selected_text 可能被清掉。
    local selected = reader_highlight.selected_text
    local snippet = cleanupForPayload(selected.text or "")
    if snippet == "" then
        UIManager:show(InfoMessage:new{ text = _("选中内容为空，请先选中一段文字/片段。") })
        return
    end

    local max_chars = tonumber(self.runtime_settings.snippet_max_chars) or self.default_settings.snippet_max_chars
    if #snippet > max_chars then
        snippet = snippet:sub(1, max_chars) .. "…"
    end

    local book_title = self:guessBookTitle(reader_highlight)
    local chapter_label = self:guessChapterLabel(reader_highlight)

    -- 菜单「共读附言：改用剪贴板」：不弹 MultiInputDialog，附言=剪贴板（系统里先复制）。
    if self.runtime_settings.co_read_note_from_clipboard then
        local user_note = readClipboardAsNote()
        if user_note == "" then
            UIManager:show(InfoMessage:new{
                text = _("已开启「附言用剪贴板」。请先用系统输入法写好附言并复制，再点「发给渡一起看」。"),
                timeout = 5,
            })
            return
        end
        local max_note = 4000
        if #user_note > max_note then
            user_note = user_note:sub(1, max_note) .. "…"
        end
        self:afterHighlightMenuClosed(reader_highlight, function()
            self:doSendToDu(book_title, chapter_label, snippet, user_note)
        end)
        return
    end

    -- 绝不能在高亮按钮 callback 栈里同步 onClose（MIUI 上易 native mutex 崩溃）。
    self:afterHighlightMenuClosed(reader_highlight, function()
        local note_dialog
        note_dialog = MultiInputDialog:new{
            title = _("共读：发给渡一起看"),
            fields = {
                { text = book_title, hint = _("书名（可改）") },
                { text = chapter_label, hint = _("章节（可改/可留空）") },
                { text = "", hint = _("附言（可选）") },
            },
            buttons = {
                {
                    {
                        text = _("Cancel"),
                        id = "close",
                        callback = function()
                            UIManager:close(note_dialog)
                        end,
                    },
                    {
                        text = _("发送"),
                        is_enter_default = true,
                        callback = function()
                            local fields = note_dialog:getFields()
                            local b = fields and fields[1] or ""
                            local c = fields and fields[2] or ""
                            local n = fields and fields[3] or ""
                            UIManager:close(note_dialog)
                            UIManager:scheduleIn(0.2, function()
                                self:doSendToDu(b, c, snippet, n)
                            end)
                        end,
                    },
                },
            },
        }
        UIManager:show(note_dialog)
        local auto_kb = true
        if Device and type(Device.isAndroid) == "function" then
            local ok, is_and = pcall(function()
                return Device:isAndroid()
            end)
            if ok and is_and then
                auto_kb = false
            end
        end
        if auto_kb and note_dialog.onShowKeyboard then
            note_dialog:onShowKeyboard()
        end
    end)
end

function CoRead:doSendToDu(book_title, chapter_label, snippet, user_note)
    local settings = self.runtime_settings or {}
    local base = (settings.gateway_base_url or ""):gsub("/$", "")
    if base == "" then
        UIManager:show(InfoMessage:new{ text = _("未配置 gateway_base_url。") })
        return
    end

    local gateway_url
    if settings.mode == "co_read_session" then
        gateway_url = base .. (settings.gateway_co_read_path or "/api/co-read/session")
    else
        gateway_url = base .. (settings.gateway_chat_path or "/v1/chat/completions")
    end

    -- 不要在「发送」按钮回调栈里直接阻塞网络：部分安卓（尤其 MIUI）容易强退/崩溃。
    -- 延后一帧再请求；发送中提示不要短 timeout 自动关，避免二次 close 把 UI 弄乱。
    local sending = InfoMessage:new{
        text = _("发送中…"),
    }
    UIManager:show(sending)

    local bearer = settings.bearer_token or ""
    local wid = settings.window_id or ""
    local mode = settings.mode

    local payload
    if mode == "co_read_session" then
        payload = {
            window_id = wid,
            book_title = book_title,
            chapter_label = chapter_label,
            snippet = snippet,
            user_note = user_note or "",
        }
    else
        payload = {
            window_id = wid,
            stream = false,
            messages = {
                {
                    role = "user",
                    content = self:buildCoReadUserMessage(book_title, chapter_label, snippet, user_note or ""),
                },
            },
        }
    end

    UIManager:scheduleIn(0.12, function()
        local function safe_close(widget)
            if not widget then return end
            pcall(function()
                UIManager:close(widget)
            end)
        end

        local function show_err(msg)
            safe_close(sending)
            UIManager:show(InfoMessage:new{ text = msg, timeout = 5 })
        end

        if NetworkMgr and NetworkMgr.isOnline and not NetworkMgr:isOnline() then
            show_err(_("网络不可用，请先联网后再试。"))
            return
        end

        local ok_enc, encoded = pcall(JSON.encode, payload)
        if not ok_enc or type(encoded) ~= "string" or encoded == "" then
            logger.err("du_co_read JSON.encode 失败: " .. tostring(encoded))
            show_err(_("请求打包失败，请重试。"))
            return
        end

        local headers = {
            ["Content-Type"] = "application/json; charset=utf-8",
            ["content-length"] = tostring(#encoded),
        }
        if wid ~= "" then
            headers["X-Window-Id"] = wid
        end
        if bearer ~= "" then
            headers["Authorization"] = "Bearer " .. bearer
        end

        local ok, result = self:postJson(gateway_url, encoded, headers)
        safe_close(sending)

        if not ok then
            local detail = ""
            if result then
                if result.detail and result.detail ~= "" then
                    detail = tostring(result.detail)
                elseif result.kind == "network_error" then
                    detail = _("无法连接网关或等待超时。")
                        .. " "
                        .. tostring(result.code or result.status or "")
                else
                    detail = tostring(result.kind or result.detail or "")
                end
            end
            if detail == "" then
                detail = _("未知错误")
            end
            UIManager:show(InfoMessage:new{
                text = _("发送失败：") .. detail,
                timeout = 8,
            })
            return
        end

        local resp = result.resp or {}
        local assistant_content = ""

        if mode == "co_read_session" then
            assistant_content = tostring(resp.du_reply or resp.reply or resp.content or resp._raw or "")
        else
            assistant_content = self:extractAssistantContent(resp)
        end

        if type(assistant_content) ~= "string" then
            assistant_content = tostring(assistant_content or "")
        end
        assistant_content = assistant_content:gsub("^%s+", "")
        if assistant_content == "" then
            assistant_content = _("已收到返回，但无法解析渡的内容。")
        end

        local scr = Device and Device.screen
        if not scr or not scr.getWidth then
            show_err(_("无法获取屏幕尺寸，回应无法在窗口中显示。"))
            return
        end
        local w = math.floor(math.min(scr:getWidth(), scr:getHeight()) * 0.95)
        local h = math.floor(math.max(scr:getHeight() * 0.55, 260))
        UIManager:show(TextViewer:new{
            title = _("渡的回应"),
            show_menu = false,
            text = assistant_content,
            width = w,
            height = h,
        })
    end)
end

return CoRead

