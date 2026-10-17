-- Merge this key binding into your existing WezTerm config.
local wezterm = require 'wezterm'
local config = wezterm.config_builder()
local root = wezterm.home_dir .. '/tools/wezterm-image-panel' -- Windows example: 'D:/Github/wezterm-image-panel'
local panel = dofile(root .. '/integrations/wezterm.lua')
local windows = (wezterm.target_triple or ''):find('windows') ~= nil
local python = root .. (windows and '/.venv/Scripts/python.exe' or '/.venv/bin/python')

config.keys = {
  {
    key = 'I', mods = windows and 'CTRL|SHIFT' or 'CMD|SHIFT',
    action = panel.action {
      command = { python, '-m', 'wezterm_image_panel' },
      size = 0.40,
    },
  },
}

return config
