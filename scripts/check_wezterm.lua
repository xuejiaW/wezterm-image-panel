-- Headless integration check: uses mocks, never opens or closes a real pane.
-- Run: wezterm --config-file scripts/check_wezterm.lua show-keys --lua
local real_wezterm = require 'wezterm'
local source = debug.getinfo(1, 'S').source:gsub('^@', ''):gsub('\\', '/')
local root = source:gsub('/scripts/[^/]+$', '')
local split, sent, notices, panes = nil, nil, 0, {}
local preview = {
  pane_id = function() return 8 end,
  get_user_vars = function() return { WEZTERM_IMAGE_PANEL_OWNER = '7' } end,
  send_text = function(_, text) sent = text end,
}
local fake = {
  action_callback = function(callback) return callback end,
  mux = { get_pane = function(id) return id == 8 and preview or nil end },
}
package.loaded.wezterm = fake
local original_debug = debug
debug = nil -- GUI callback Lua contexts can omit the debug library.
local panel = dofile(root .. '/wezterm_integration.lua')
debug = original_debug
local window = { toast_notification = function() notices = notices + 1 end }
local pane = {
  pane_id = function() return 7 end,
  get_user_vars = function() return {} end,
  tab = function() return { panes = function() return panes end } end,
  get_foreground_process_info = function() return { pid = 42 } end,
  get_current_working_dir = function() return { file_path = '/demo' } end,
  get_title = function() return 'Demo task' end,
  split = function(_, options) split = options end,
}
local command = { '/demo path/python3', '/demo path/wezterm_image_panel.py' }
panel.action { command = command, size = 0.35 }(window, pane)
assert(split.direction == 'Right' and split.size == 0.35)
assert(split.args[1] == command[1] and split.args[2] == command[2])
assert(split.args[3] == 'auto-view' and split.args[4] == '--source-pid')
assert(split.args[5] == '42' and split.args[#split.args] == '7')
assert(#command == 2, 'Do not mutate the caller command array')
split = nil
fake.target_triple = 'x86_64-pc-windows-msvc'
panel.toggle(window, pane, {root='D:/demo path'})
assert(split.args[1] == 'python' and split.args[2] == 'D:/demo path/wezterm_image_panel.py')
split = nil
panes = { preview }
panel.toggle(window, pane)
assert(sent == 'q\n' and split == nil, 'Close the owned preview, not the source')
panes = {}
pane.get_foreground_process_info = function() return nil end
panel.toggle(window, pane)
assert(notices == 1 and split == nil)
package.loaded.wezterm = real_wezterm
return { keys = {} }
