--[[--
@module koplugin.du_co_read
--]]

local Dispatcher = require("dispatcher") -- luacheck:ignore
local DataStorage = require("datastorage")
local InfoMessage = require("ui/widget/infomessage")
local InputDialog = require("ui/widget/inputdialog")
local MultiInputDialog = require("ui/widget/multiinputdialog")
local TextViewer = require("ui/widget/textviewer")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local LuaSettings = require("luasettings")
local _ = require("gettext")

local JSON = require("json")
local logger = require("logger")

local util = require("util")
local Device = require("device")
local Screen = Device.screen

local http = require("socket.http")
local ltn12 = require("ltn12")
local socket = require("socket")
local socketutil = require("socketutil")

local CoRead = WidgetContainer:extend{
    name = "du_co_read",
    is_doc_only = false,
}

local SETTINGS_FILE = "du_co_read.lua"

CoRead.default_settings = {
    -- 网关基址，例如 http://127.0.0.1:5000
    gateway_base_url = "http://127.0.0.1:5000",
    -- 目前仓库已实现：/v1/chat/completions（插件默认走它可先跑通）
    gateway_chat_path = "/v1/chat/completions",
    -- 文档约定：/api/co-read/session（后续你实现后可切换到这里）
    gateway_co_read_path = "/api/co-read/session",
    -- chat | co_read_session
    mode = "co_read_session",
    -- 用于区分窗口记忆；建议填一个稳定值（例如 koreader）
    window_id = "koreader",
    -- 可选：当你的网关需要额外鉴权时填 Bearer Token
    bearer_token = "",
    -- 单次上送片段最大字符数（超长会截断）
    snippet_max_chars = 4000,
}

function CoRead:readSettings()
    local s = LuaSettings:open(DataStorage:getSettingsDir() .. "/" .. SETTINGS_FILE)
    s:readSetting("du_co_read", self.default_settings)
    return s
end

function CoRead:loadRuntimeSettings()
    local raw = self.settings:readSetting("du_co_read", self.default_settings) or {}
    -- 简单兜底，避免 nil
    for k, v in pairs(self.default_settings) do
        if raw[k] == nil then raw[k] = v end
    end
    self.runtime_settings = raw
end

function CoRead:saveRuntimeSettings()
    self.settings:saveSetting("du_co_read", self.runtime_settings)
    self.settings:flush()
end

function CoRead:init()
    self.ui.menu:registerToMainMenu(self)
    self.settings = self:readSettings()
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
        },
    }
end

function CoRead:showSettingDialog(title, current_value, setter)
    local dlg = InputDialog:new{
        title = title,
        input = tostring(current_value or ""),
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
                        local v = dlg:getInputText()
                        setter(v)
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
    if self._highlight_button_added then
        return
    end
    if not (self.ui and self.ui.highlight and self.ui.highlight.addToHighlightDialog) then
        return
    end

    -- 挂在“选中高亮菜单”里；前提是你的 KOReader 长按默认动作需要弹出选择/编辑菜单（而不是直接查词）。
    self.ui.highlight:addToHighlightDialog("du_co_read_send", function(reader_highlight)
        return {
            text = _("发给渡一起看"),
            -- enabled 字段尽量用布尔值（避免不同版本里函数式 enabled 不生效）。
            enabled = true,
            callback = function()
                CoRead.onSendSelectedToDu(self, reader_highlight)
                -- 不强制 onClose()：避免打断用户后续手势；你也可以改成 reader_highlight:onClose()
            end,
        }
    end)

    self._highlight_button_added = true
end

local function cleanupForPayload(s)
    s = tostring(s or "")
    -- 替换掉明显的多余空白，避免 token 浪费
    s = s:gsub("%s+", " ")
    s = s:sub(1, 50000)
    return s
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

function CoRead:postJson(url, payload, headers)
    local response_chunks = {}
    local body = JSON.encode(payload)

    local request = {
        url = url,
        method = "POST",
        headers = headers or {},
        source = ltn12.source.string(body),
        sink = ltn12.sink.table(response_chunks),
    }

    -- 适度超时（避免卡死）
    socketutil:set_timeout(10, 30)
    local code, resp_headers, status = socket.skip(1, http.request(request))
    socketutil:reset_timeout()

    if resp_headers == nil then
        return false, { kind = "network_error", code = code, status = status, body = nil }
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

function CoRead:onSendSelectedToDu(reader_highlight)
    if not (reader_highlight and reader_highlight.selected_text) then
        UIManager:show(InfoMessage:new{ text = _("未获取到选中内容。") })
        return
    end

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

    local note_dialog = MultiInputDialog:new{
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
                        self:doSendToDu(b, c, snippet, n)
                    end,
                },
            },
        },
    }
    UIManager:show(note_dialog)
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

    local sending = InfoMessage:new{
        text = _("发送中…"),
        timeout = 0.6,
    }
    UIManager:show(sending)

    local bearer = settings.bearer_token or ""
    local headers = {
        ["Content-Type"] = "application/json",
    }
    if bearer ~= "" then
        headers["Authorization"] = "Bearer " .. bearer
    end

    local payload
    if settings.mode == "co_read_session" then
        -- 未来模式：按文档直接调用共读会话接口
        payload = {
            window_id = settings.window_id or "",
            book_title = book_title,
            chapter_label = chapter_label,
            snippet = snippet,
            user_note = user_note or "",
        }
    else
        -- 当前可跑通模式：走网关已有的 OpenAI 兼容 chat 管道
        payload = {
            window_id = settings.window_id or "",
            stream = false,
            messages = {
                {
                    role = "user",
                    content = self:buildCoReadUserMessage(book_title, chapter_label, snippet, user_note or ""),
                },
            },
        }
    end

    local ok, result = self:postJson(gateway_url, payload, headers)
    UIManager:close(sending)

    if not ok then
        UIManager:show(InfoMessage:new{ text = _("发送失败：") .. tostring(result.kind or "") })
        return
    end

    local resp = result.resp or {}
    local assistant_content = ""

    if settings.mode == "co_read_session" then
        -- co-read session 返回字段在你实现后再对齐；这里先做兜底
        assistant_content = tostring(resp.du_reply or resp.reply or resp.content or resp._raw or "")
    else
        assistant_content = self:extractAssistantContent(resp)
    end

    assistant_content = assistant_content:gsub("^%s+", "")
    if assistant_content == "" then
        assistant_content = _("已收到返回，但无法解析渡的内容。")
    end

    local w = math.floor(math.min(Screen:getWidth(), Screen:getHeight()) * 0.95)
    local h = math.floor(math.max(Screen:getHeight() * 0.55, 260))
    UIManager:show(TextViewer:new{
        title = _("渡的回应"),
        show_menu = false,
        text = assistant_content,
        width = w,
        height = h,
    })
end

return CoRead

