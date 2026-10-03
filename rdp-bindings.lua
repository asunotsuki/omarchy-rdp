-- Keep Omarchy's local Alt+Tab behavior except while our RDP window is active.
-- Disable the local bindings there: native key down/up events (including held
-- Alt and Shift) reach FreeRDP without synthesized shortcuts or keyboard grabs.
hl.unbind("ALT + TAB")
hl.unbind("ALT + SHIFT + TAB")

local function cycle(next_window)
  return function()
    hl.dispatch(hl.dsp.window.cycle_next({ next = next_window }))
    hl.dispatch(hl.dsp.window.bring_to_top())
  end
end

local forward = hl.bind("ALT + TAB", cycle(true), {
  description = "Next window (inside Windows when RDP is focused)",
})
local backward = hl.bind("ALT + SHIFT + TAB", cycle(false), {
  description = "Previous window (inside Windows when RDP is focused)",
})

local function update()
  local window = hl.get_active_window()
  local function is_rdp(class)
    return type(class) == "string" and class:match("^omarchy%-rdp%-[A-Za-z0-9_-]+$") ~= nil
  end
  local enabled = not (window and (is_rdp(window.class) or is_rdp(window.initial_class)))
  forward:set_enabled(enabled)
  backward:set_enabled(enabled)
end

hl.on("window.active", update)
hl.on("window.class", update)
update() -- Also handle config reload while an RDP session is already focused.
