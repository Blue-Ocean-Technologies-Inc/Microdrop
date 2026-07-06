## v1.1.0 (2026-07-06)

### Feat

- **application**: extra_plugins_loaded event fired after group-plugin restore
- **utils**: ToggleEditor accepts non-string on/off values

### Fix

- **logging**: demote the per-message listener log to debug

### Refactor

- **utils**: move the in-place toggle into traitsui_qt_helpers; name both toggles
- **plugin-management**: drop redundant version from plugin manifests

## v1.0.0 (2026-07-06)

### Feat

- launch-time plugin update check (background fetch + dialog)
- update-check dialog view + controller (Update All -> relaunch)
- update-check diff model (compute_update_report + UpdateDialogModel)
- installed_plugin_dists() — installed MicroDrop plugin dist versions
- priority ordering for contributed status-bar icons
- register StatusBarPlugin in frontend plugin list
- BaseStatusPlugin contributes to status_bar_icons extension point
- microdrop_status_bar plugin with status_bar_icons extension point
- **plugin-management**: split device groups into UI/backend + group-managed protocol controls
- **plugin-management**: full Manage Plugins window (apply/install/uninstall)
- **plugin-management**: Browse Plugins dialog (install from channel)
- **plugin-management**: threaded progress helper + relaunch into pixi env
- **plugin-management**: conda-channel package installer + app-data cache
- **plugin-management**: manifest-aware group registry
- **plugin-management**: TOML manifest parser + entry-point discovery
- **plugin-management**: Manage Plugins menu action + service + launch restore
- **plugin-management**: Manage Plugins dialog (toggle groups)
- **plugin-management**: PluginGroupManager with built-in Z-Stage/heater groups
- **plugin-management**: reactive TASK_EXTENSIONS mounting
- **status-panes**: on_live_mounted hook for runtime hot-mounts
- **utils**: runtime add/remove of dock panes + live menu-bar rebuild
- **peripherals_ui**: PeripheralMessageHandler on the shared base
- **heater-plots**: teardown the plot listener on pane destroy
- **status-panes**: destroy() teardown on BaseStatusDockPane
- **status-panes**: teardown() on BaseMessageHandler + interface
- **utils**: unregister helper for dramatiq listener actors
- **heater-plots**: Pause and Stop buttons on the plot pane
- **heater**: add live temperature/PWM plotting dock pane
- **heater-config**: show a scan summary label after a sensor scan
- **status-panes**: add RealtimeModeIconMixin
- **ppt-status**: freeze timers around StepContext.wait_for
- **ppt-status**: wire ack-wait signals to the status model
- **ppt-status**: add ack_wait_started/finished executor signals
- **ppt-status**: freeze status timers during acknowledgement waits
- **ppt-status**: add ScopeStopwatch.is_stopped_at_zero() helper
- **heater**: heater temperature protocol column (Phase B)
- **heater**: protocol set-temperature with reached-within-tolerance ack (Phase A)
- **heater_ui**: Save & push to board button (Phase 3)
- **heater**: save-config-to-board push via mpremote (Phase 3)
- **heater_ui**: available-sensors reference + HTML de-emphasized labels
- **utils**: add HtmlLabelEditor (rich-text QLabel bound to a Str trait)
- **heater_ui**: edit + save the sensor/heater config (Phase 2)
- **heater**: pydantic validation for sensor/heater config edits
- **heater_ui**: wire the configure-sensors dialog into the app
- **heater_ui**: configure-sensors dialog (Phase 1, read-only)
- **heater**: backend config ops for the sensor/heater configurator
- **peripheral**: publish search-stopped when the monitor thread terminates
- **status-icons**: flip the status-icon tooltip while searching
- **status**: add a searching trait to BaseStatusModel
- **peripherals_ui**: re-enable the Z-Stage status icon if a scan stalls for 10s
- **heater_ui**: re-enable the status icon if a scan stalls for 10s
- **peripherals_ui**: make the Z-Stage status icon search for a connection
- **heater_ui**: gate the status-icon connection search on an active scan
- **peripheral**: publish a connection-search signal from the monitor
- **heater_ui**: make the status-bar heater icon search for a connection on click
- **utils**: add ClickableLabel (QLabel with a clicked signal)
- **heater_ui**: stretch collapsible sections to full pane width
- **utils**: add stretch_group_layouts_horizontally helper
- **heater_ui**: make the heater pane resizable and scrollable
- **heater_ui**: render section collapse toggles as arrow glyphs
- **utils**: add IconToggleEditor (Material-glyph Bool toggle)
- **heater_ui**: make every control section collapsible
- **heater_ui**: add per-section collapse toggles
- **heater_ui**: restyle the mode switch and reorder the control group
- **heater_ui**: track live PID duty in the PWM setpoint during Temp mode
- **heater_ui**: default the mode switch to Temp (closed-loop PID)
- **utils**: expose full Toggle colour args on the toggle editors
- **heater_ui**: render the PWM/Temp mode switch as an AnimatedToggle
- **utils**: add AnimatedToggle slider widget + AnimatedEnumToggleEditor
- **heater_ui**: toggle PWM/Temp mode with a button instead of a radio
- **utils**: add EnumToggleEditor for two-state Enum/Str traits
- **heater_ui**: render a status row per heater via ListEditor
- **heater_ui**: per-heater status readouts driven by PID_<HEATER> frames
- **heater_ui**: PWM/Temp mode radio in view, per-mode setpoint enable
- **heater_ui**: gate heater commands behind streaming, apply mode on start
- **heater_ui**: replace PID toggle with PWM/Temp mode radio in model
- **heater**: gate temperature setpoint behind PID + 'applies when PID starts' warning
- **heater_controls_ui**: enabling PID auto-starts streaming
- **heater_controls_ui**: push current setpoint when PID is enabled
- **manual_controls**: configurable labels on ToggleEditor + add heater icon
- **heater_controls_ui**: dock pane for heater monitoring + control
- **heater_controller**: publish telemetry + whoami on connect
- **heater_controller**: typed command topics + heater discovery
- **examples**: register HeaterControllerPlugin + add heater backend demo
- **heater_controller**: backend plugin for the heater via the base classes
- **backend**: add generic peripheral_device_controller_base package
- **device_viewer**: seed device repo with bundled SVG files on first run
- **#477**: route-rep time-expired dialog + dynamic-loop decision logging
- **#477**: warn before leaving idle phase on phase-bar seek
- **#477**: phase bar shows unique phases + dark-yellow idle cell
- **#477**: guaranteed-loop gate, idle phase, seek re-entry, mid-loop-expiry
- **#477**: executor signals + controller wiring for dynamic phase/idle
- **#477**: status model unique-phase + idle state for dynamic loops
- **#477**: pure duration-loop gate + idle-cell helpers
- **#477**: warn before leaving idle phase on phase-bar seek
- **#477**: phase bar shows unique phases + dark-yellow idle cell
- **#477**: guaranteed-loop gate, idle phase, seek re-entry, mid-loop-expiry
- **#477**: executor signals + controller wiring for dynamic phase/idle
- **#477**: status model unique-phase + idle state for dynamic loops
- **#477**: pure duration-loop gate + idle-cell helpers
- persist protocol-tree column order across restarts
- **advanced-mode**: device viewer editable + actuation write-back in a run (#434)
- **advanced-mode**: keep protocol tree editable + live-apply edits in a run (#434)
- **advanced-mode**: thread advanced_mode through the protocol context (#434)
- **volume-threshold**: add Rewind recovery action
- **protocol-tree**: separate Step Rep and Phase Rep selectors side by side
- **protocol-tree**: jump to a specific step repetition from the timeline
- **protocol-tree**: step-rep collapse + show-full timeline expansion
- **protocol-tree**: collapse phase reps to base loop + Rep selector
- **protocol-tree**: throttle timeline drag seeks
- **protocol-tree**: group tint bands + relative drag in timeline
- **protocol-tree**: show phase track only while protocol is running
- **protocol-tree**: timeline current item as a highlighted cell box
- **protocol-tree**: wire TimelineBar seeks through the controller
- **protocol-tree**: mount TimelineBar under the nav bar
- **protocol-tree**: add TimelineBar seek widget (view)
- **device-viewer**: load persisted calibration data at startup
- **device-viewer**: persist calibration capacitances to preferences
- **protocol-tree**: persist and restore column visibility in the tree widget
- **protocol-tree**: add column-visibility persistence store
- **run-script**: add --plugins arg to select frontend/backend/services layers
- **message-prompt**: offer Continue / Stay Paused choice at the gate
- **dialogs**: tag secondary buttons with explicit role
- **plugin**: register message-prompt column in the builtin set
- **columns**: add per-step message-prompt column
- **executor**: add pause/resume + worker-thread wait() primitive
- **device-viewer**: route rotation through model + apply at startup
- **device-viewer**: load persisted device-view rotation on startup
- **device-viewer**: persist device-view rotation on model
- wire up reboot action with confirmation warning
- add dropbot reboot request handler
- gamepad remapping, hot-plug, live capture, and reconnect
- add gamepad connection indicator to status bar
- add joystick icon glyph for gamepad indicator
- add simulation buttons for shorts, halt, and chip toggle
- add mock dropbot plugin lists to plugin_consts.py
- add warning dialog when leaving free mode with unsaved changes (#278)
- add popup warning when starting protocol with active video recording (#279)

### Fix

- silent skip on any update-check failure; drop unused logger
- build status bar at application_initialized, not active_window
- guard status-bar icon container access against destroyed window at shutdown
- **plugin-management**: device group plugins have ONE loader — the group manager
- **plugin-management**: startup crash from early restore + broken adoption
- **app**: keep splash screen on top while the app boots
- **heater**: re-apply @observe on the _populate_status_bar override
- **heater**: resolve protocol target to the real board heater channel
- **heater_ui**: drop the readouts scroll area so the height cap is tight
- **heater_ui**: stop the heater-status list from leaving a big vertical gap
- **heater_ui**: refresh from board clears the scan (status back to In config)
- **heater_ui**: refresh updates the config tables in place + size columns to content
- **heater_ui**: show the full wrapped help text in the configurator
- **heater_ui**: wrap the configurator help text so it doesn't widen the pane
- **heater_ui**: disable the status icon immediately on a search click
- **peripheral**: re-announce search state on every start request
- **utils**: only stretch section boxes, keep their contents left-aligned
- **utils**: use Qt.AlignmentFlag.* in stretch helper
- **heater_ui**: log telemetry parse failures instead of swallowing them
- **utils**: wrap Toggle bar/handle colours in QColor
- **heater_ui**: correct main temp/PWM readouts from real board frames
- **heater_ui**: select main PWM readout by frame, mirroring old UI
- **manual_controls**: ToggleEditor label now updates on click, not just trait
- restore files unintentionally bundled-out of earlier commits
- drop dead EXPERIMENTAl_PLUGINS import in frontend run script
- **#477**: show time-expired dialog while paused; complete-loop stops at start
- **#477**: wake held phase when rep-duration budget is crossed so overrun dialog fires
- **#477**: keep dyn_loop_active set during dynamic loop so timeline shows one loop
- **#477**: in-loop seek checkpoint so mid-loop phase toggles reposition in place
- **#477**: dyn_loop_active flag fixes seek phase_total, idle preview, stale dyn_idle, static idle-tint (final review)
- **#477**: cap per-phase hold at duration_s for the worst-case loop bound
- **#477**: resolve dynamic-loop resume phase from resume_target (review)
- **#477**: keep dyn_loop_active set during dynamic loop so timeline shows one loop
- **#477**: in-loop seek checkpoint so mid-loop phase toggles reposition in place
- **#477**: dyn_loop_active flag fixes seek phase_total, idle preview, stale dyn_idle, static idle-tint (final review)
- **#477**: cap per-phase hold at duration_s for the worst-case loop bound
- **#477**: resolve dynamic-loop resume phase from resume_target (review)
- **advanced-mode**: keep viewer editable when navigating steps mid-run (#434)
- **advanced-mode**: on_live_edit receives the ProtocolContext, not a StepContext (#434)
- **advanced-mode**: lock device viewer during a run unless advanced (#434)
- **volume-threshold**: rewind to furthest leading edge on multi-channel hit
- **protocol-tree**: update status bar immediately on timeline rep change
- **protocol-tree**: step-rep combo live-updates and full-view frames drag
- **protocol-tree**: live-update Step Rep combo as repetitions advance
- **protocol-tree**: collapse phases off real base loop; show rep controls idle
- **protocol-tree**: count distinct steps, compact rep label in status bar
- **protocol-tree**: timeline follows direct tree selection changes
- **protocol-tree**: highlight current step tick; show phase ticks on selected step
- **protocol-tree**: theme-aware TimelineBar running accent; drop dead color key; test _phase_index_at_x
- **dialogs**: drive confirm button colors by role, drop dead overrides
- **message-prompt**: harden pause/resume/wait against hangs and headless runs
- replace QTimer with threading for capacitance stream
- address code review issues in mock dropbot plugins
- remove unused imports in mock_controller.py

### Refactor

- run the launch update check via a dramatiq actor
- strip gamepad indicator from StatusBarManager
- device_viewer contributes joystick + recording icons via extension point
- move status-bar creation out of MicrodropTask into microdrop_status_bar
- BaseStatusDockPane contributes status-bar icons via extension point
- extract heater + magnet/Z-Stage stacks into standalone plugin packages
- decouple src from the heater / Z-Stage device stacks
- **peripherals_ui**: drop the superseded dramatiq controller pair
- **peripherals_ui**: move the plugin onto BaseStatusPlugin
- **peripherals_ui**: move the Z-Stage pane onto BaseStatusDockPane
- **peripherals_ui**: own status colors + template contract on the model
- **heater-plots**: plot model to proper traits + pause/stop/hidden/revision state
- **heater**: use the template's status-bar hooks instead of overriding wholesale
- **status-panes**: move dropbot/mock/opendrop panes to the new template
- **status-panes**: make BaseStatusDockPane device-neutral
- **peripherals**: each peripheral plugin owns its startup search + menu
- **peripheral**: publish searching state via a _searching observer
- **peripherals_ui**: simplify Z-Stage status-icon search to backend-ack only
- **heater_ui**: simplify status-icon search to backend-ack only
- **heater_ui**: move the Search Connection menu into the heater plugin
- **utils**: replace button EnumToggleEditor with Toggle/AnimatedToggle editors
- **heater_ui**: rename stream-off setpoint warning + preference
- **menus**: move heater connection search into peripherals Tools menu
- **heater_controls_ui**: simplify pane to PID + Stream toggles
- **heater_controls_ui**: rebuild on the status-and-controls template
- **peripheral_controller**: re-parent magnet onto peripheral_device_controller_base
- replace device-viewer-sync Qt signal bridge with trait Events
- **protocol-tree**: DRY step seek/preview helper; unconditional timeline running accent
- **dialogs**: classify dialog buttons by explicit role only
- decouple frontend/backend via pub/sub topics

### Perf

- **heater-plots**: persistent artists, gated redraws, clickable legend


- remove traits model.
