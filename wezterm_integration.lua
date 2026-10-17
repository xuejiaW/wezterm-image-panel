local wezterm = require 'wezterm'
local M = {}

local function close_panel(id)
  -- CloseCurrentPane follows GUI focus and can close the source Codex pane.
  -- Address our preview explicitly; do not block the GUI waiting for its IPC.
  local panel = wezterm.mux.get_pane(id)
  if panel then panel:send_text('q\n') end
end

function M.toggle(window, pane, options)
  options = options or {}
  local source_id = pane:pane_id()
  local vars = pane:get_user_vars()
  if vars.WEZTERM_IMAGE_PANEL_OWNER then
    close_panel(source_id)
    return
  end
  -- Owner metadata survives configuration reloads and Lua callback contexts.
  for _, candidate in ipairs(pane:tab():panes()) do
    if candidate:get_user_vars().WEZTERM_IMAGE_PANEL_OWNER == tostring(source_id) then
      close_panel(candidate:pane_id())
      return
    end
  end
  local info = pane:get_foreground_process_info()
  if not info then
    window:toast_notification('WezTerm Image Panel', '无法获取当前窗格的进程。此快捷键用于本机 Codex。', nil, 4000)
    return
  end
  local cwd_url = pane:get_current_working_dir()
  local cwd = cwd_url and cwd_url.file_path or ''
  local python = (wezterm.target_triple or ''):find('windows') and 'python' or 'python3'
  local command = options.command
  if not command and options.root then
    command = { python, options.root .. '/wezterm_image_panel.py' }
  end
  if not command then
    window:toast_notification('WezTerm Image Panel', 'Set command or root in panel.action options.', nil, 4000)
    return
  end
  local args = {}
  for _, value in ipairs(command) do table.insert(args, value) end
  for _, value in ipairs {
    'auto-view', '--source-pid', tostring(info.pid),
    '--source-title', pane:get_title(), '--source-cwd', cwd,
    '--source-pane', tostring(source_id),
  } do table.insert(args, value) end
  pane:split {
    direction = 'Right', size = options.size or 0.40,
    args = args,
  }
end

function M.action(options)
  return wezterm.action_callback(function(window, pane)
    M.toggle(window, pane, options)
  end)
end

function M.register_test_event(name, options)
  -- Optional development harness invokes the exact same shortcut callback.
  wezterm.on(name, function(window, pane) M.toggle(window, pane, options) end)
end

return M
