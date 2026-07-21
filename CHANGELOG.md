## v1.3.1 (2026-07-21)

### Refactor

- **microdrop_utils**: use QToolButton for glyph editors
- **device_viewer**: drop the raw-frame capture path

### CI

- state-based release detection — merge-method-proof, recursion-free

## v1.3.0 (2026-07-21)

### Feat

- **user_help_plugin**: prefer GitHub-styled markdown render, offline fallback
- **microdrop_utils**: GitHub-styled markdown page render with shared tag-token escaping
- **examples**: mock-changelog render demo for What's New + Changelog viewer
- **user_help_plugin**: Changelog help menu item rendering CHANGELOG.md
- **microdrop_utils**: markdown_text_to_html QTextDocument helper
- **microdrop_application**: What's New startup dialog for new changelog sections
- **microdrop_application**: CHANGELOG_PATH constant
- **microdrop_utils**: changelog delta helper for prepend-style changelogs
- **user_help_plugin**: move Download MicroDrop Launcher into its own bottom menu group
- **user_help_plugin**: show only the rendered launcher README in the help dialog
- **microdrop_application**: WebViewDialog accepts html_content for direct HTML rendering
- **microdrop_utils**: add helper rendering GitHub markdown files to standalone HTML
- **user_help_plugin**: add Download MicroDrop Launcher help menu item
- **user_help_plugin**: add architecture html path and launcher README url constants
- **microdrop_application**: add generic WebViewDialog for HTML/web content
- **pluggable_protocol_tree**: on_row_loaded column hook after load
- **pluggable_protocol_tree**: handle add-step requests, identify groups
- **pluggable_protocol_tree**: add-step topic + group id on row_selected
- **pluggable_protocol_tree**: route reps lock honors mode dialog
- **pluggable_protocol_tree**: bulk set skips locked cells
- **pluggable_protocol_tree**: enforce column locks in MvcTreeModel
- **pluggable_protocol_tree**: owner-keyed column locks on BaseRow
- **microdrop_application**: add choose() multi-choice dialog
- **microdrop_utils**: configurable dramatiq worker settings via json
- **microdrop_utils**: self-update source repo at launch
- **plugin_management**: gate the upgrade glyph
- **plugin_management**: hot-load plugin reinstalls
- **plugin_mgmt**: hot-load installs, skip relaunch
- **plugin_management**: add hot-load gate
- **plugin_management**: compute requires_relaunch from diff
- **plugin_management**: add pixi env snapshot and diff
- **microdrop_utils**: mark enum cells with a chevron
- **dropbot_controller**: add validated publisher for shorts detected
- **traitsui_qt_helpers**: draw real dropdown arrow on EnumSelectColumn cells
- **plugin_management**: version picker + hide installed in Browse Plugins
- **plugin_management**: collapsible details + always-on version combos
- **traitsui_qt_helpers**: controller base + persistent-editor helpers
- **plugin_management**: per-row install/uninstall + refresh handler
- **plugin_management**: tabbed Manage Plugins with installed-packages table
- **plugin_management**: installed-package rows + details model
- **package_installer**: version-pinned install + upgrade helper

### Fix

- **microdrop_application**: re-enable What's New cache refresh
- **microdrop_utils**: escape tag-like tokens before QTextDocument markdown render
- **dialogs**: open help-document links in the system browser
- **pluggable_protocol_tree**: rebuild column load-state on add-step insert
- **video_protocol_controls**: repaint capture_at on capture toggle
- **protocol_tree_sync**: track realtime mode state and gate actuation publishing correctly
- **dropbot_monitor**: harden connection handlers in monitor mixin service
- **dramatiq_dropbot_serial_proxy**: unify connect/disconnect monitor event wrappers
- **device_viewer_sync**: Do not publish when realtime mode toggles on in free mode.
- **device_viewer**: return to draw mode once a protocol ends
- **plugin_management**: refresh details on change
- **plugin_management**: stop swallowing uninstall errors
- **plugin_management**: surface hot-load refusal reasons
- **plugin_management**: drop installed rows after install
- **plugin_management**: snapshot modules before discovery
- resolve final review issues in hot-load
- **plugin_management**: relaunch via the microdrop task
- **plugin_management**: sync env after pixi add/remove
- **microdrop_application**: report no-shorts on a user-requested check
- **microdrop_application**: make the suppress-no-shorts preference persist
- Revert "feat(traitsui_qt_helpers): draw real dropdown arrow on EnumSelectColumn cells"
- **plugin_management**: crash when changing version repeatedly
- **plugin_management**: version dropdown back to click-to-edit
- **plugin_management**: version dropdown stuck after declining install

### Refactor

- **user_help_plugin**: single OpenMarkdownDialogAction for local and remote markdown
- **microdrop_utils**: fetch raw GitHub markdown; drop GitHub-API render pipeline
- **microdrop_application**: render What's New markdown via shared helper
- **user_help_plugin**: replace About/Feedback dialog classes with generic WebViewDialog action
- **microdrop_application**: move WebViewDialog size defaults to dialogs consts
- **mock_dropbot**: publish/consume shorts via the validated model
- **dropbot_controller**: publish shorts via the validated publisher
- **traitsui_qt_helpers**: add reusable table column types

### Docs

- add ppt fluorescence-support-topics implementation plan
- **pluggable_protocol_tree**: fix stale RepeatDurationHandler docstring
- add column-locks + choose-dialog implementation plan
- **plugin_management**: allow smokes in hot-load plan
- **plugin_management**: plan hot-load implementation
- **plugin_management**: drop update-all from hot-load scope
- **plugin_management**: spec hot-load without relaunch
- **MESSAGES**: document the shorts detected payload contract
- **examples**: reuse real view/controller in installed-packages demo
- **examples**: add installed-packages table demo runner

### CI

- quote tag-and-release if expression — unquoted 'chore: release' breaks YAML
- changelog lists all conventional commit types
- RELEASE_PAT fallback for org-blocked PR creation
- reopen release PR if the previous one was closed without merging
- PR-based releases — bot opens release PR, tag on merge
- auto-release on push to main via commitizen bump

### Test

- **plugin_management**: fix collision refusal

### Chore

- **device_viewer**: lower message-buffer publish log to debug
- **dropbot_tools_menu**: clarify chip-inserted connection log message

## v1.2.0 (2026-07-15)

### Feat

- **plugin_management**: read plugin docs URL from distribution metadata
- **pluggable_protocol_tree**: add Unfold Group action and grouping shortcuts
- **device_viewer**: inline text-editor channel labels
- **protocol-tree**: WASD step nav, Ctrl+arrow phase nav shortcuts
- **quick-actions**: keyboard shortcuts + auto-append to tooltips
- **protocol-tree**: keyboard shortcuts for the navigation-bar buttons
- **protocol-tree**: keep horizontal scroll when switching steps
- **protocol-tree**: Escape clears the step selection to free mode
- **protocol-tree**: Fold into Group context-menu action
- **protocol-tree**: generic row_selected/set_cell cell sync
- **protocol-tree**: add stop-aware ctx.sleep with timer freeze
- **device-viewer**: crop/export any recording + auto-fit on align flip
- **device-viewer**: move camera preferences to a Video Settings tab
- **video-protocol-controls**: use step dotted path as recording step id
- **device-viewer**: video recording preferences
- **device-viewer**: interchangeable, preference-driven video recorders
- **device-viewer**: pin constant-quality encoding on the recorder
- **device-viewer**: Recording Viewer dock pane
- **device-viewer**: native hardware recording + alignment sidecar
- **utils**: stepped slider editor for fixed-increment float ranges
- **device-viewer**: Live feed checkbox for provider camera sources
- **protocol-tree**: dialog-editing views via edit_dialog hook
- **device-viewer**: raw-only ASI captures; no recording for provider feeds
- **microdrop_utils**: icon-button and dynamic-combo traitsui editors
- **device-viewer**: camera-source extension point
- **device-viewer**: throttle tooltip-redraw debug line
- **logger**: drop third-party DEBUG by record pathname
- **logger**: repo-only debug mode + throttled hot-path logs
- **microdrop-utils**: whoami port identity probe
- **device-viewer**: label_geometry anchor helper
- **device-viewer**: flatten curved SVG segments

### Fix

- **dock-panes**: don't force-show hot-mounted dock panes
- **quick-actions**: skip tooltip shortcut suffix when there is no shortcut
- **protocol-tree**: forward run-bracket hooks to compound handlers
- **video-protocol**: capture step_id uses dotted path to match recording scheme
- **plugin_management**: restore saved layout after hot-loaded panes mount
- **device-viewer**: keep alpha settings adjustable while protocol runs
- **application**: tolerate no-Redis at menus import
- **device-viewer**: ignore protocol-side route colors
- **device-viewer**: apply display state as a diff, not reset-rebuild
- **protocol-tree**: route execution mirrors the device viewer
- **utils**: stepped slider readout follows user drags
- **peripherals**: announce monitor shutdown without reading _searching
- **plugin-management**: persist group toggles in app preferences
- **logger**: write log files as utf-8
- ascii arrows in log messages
- **microdrop-utils**: never fall back to a busy port
- **device-viewer**: re-pivot label rotation on refit
- **device-viewer**: draw channel labels above all shapes
- **device-viewer**: anchor channel labels inside the shape
- **device-viewer**: repair electrode rings at the source
- **device-viewer**: keep largest lobe of repaired rings
- **device-viewer**: repair self-intersecting rings

### Refactor

- **protocol_quick_action_tools**: move New Group shortcut to Ctrl+Shift+Return
- **quick-actions**: carry the dock pane in the action context
- **device-viewer**: render-perf review cleanups
- **device-viewer**: typed traits in RouteExecutionService
- **utils**: fold the plan builder into the params entry point
- **utils**: centralize route-execution planning
- **device-viewer**: feed-owned streaming replaces Live feed checkbox
- **device-viewer**: repair rings in one place

### Perf

- **device-viewer**: move capture PNG saves off the GUI thread
- **device-viewer**: cap preview frame rate without touching recordings
- **device-viewer**: skip whole-model serialization during route playback
- **device-viewer**: gamepad poll idles without a controller
- **device-viewer**: recolor proportional to what changed
- **device-viewer**: repaint only changed items, cache static geometry
- **device-viewer**: stop rendering provider camera frames in video layer

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
