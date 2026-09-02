## [v1.17.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.17.0) (2026-09-01)

### Feat

- **portable**: magnet and heater protocol columns plugin ([`9ef4e11`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9ef4e11857a2f351b2141a1fef4f67963ebbc70e))
- **portable**: protocol-step magnet and heater backend contracts ([`a74fcbd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a74fcbd14b745b69c93f68edc129c39171953b00))
- **device-viewer**: tap-to-delete column in the routes table ([`8ba2918`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8ba29186e1cc91e89b10a15e87426be503893497))

### Fix

- **protocol-tree**: type the status freeze lock by the lock class ([`c6a422b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c6a422b43bbd74242ee041041b8ef45c808cf33f))
- **protocol-tree**: tap a selected cell to edit on the touchscreen ([`01f21c6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/01f21c6e948e9de59b765859e592f5778dec4635))

### Docs

- **messages**: portable protocol column flow ([`fa197c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fa197c1783b7c34d688885dba8c5f3cc06ad7f2a))

### CI

- **release**: update the release PR through the REST API ([`d073a12`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d073a125b6532637acbc17c667c54eeeb5a2a435))

### Chore

- **device-viewer**: bring route model and table view ruff-clean ([`e23d1aa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e23d1aa40c089738f8984b8fbe61fa988e57576e))

## [v1.16.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.16.0) (2026-09-01)

### Feat

- **portable**: touch access to tooltips and electrode menu items ([`4fbfadc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4fbfadcd69f4ed9ca37f95cfff97ce9ae9f4e10e))
- **portable**: long press posts a right-click context menu ([`09c1d46`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/09c1d46f9a95991992cf62c6b8b3b4429a2f10ff))
- **portable**: pinch zoom and touch flick scrolling ([`3e672dc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3e672dcf9744a56add8b292cd8ed2347f6dedfaa))

### Fix

- **app**: keep touch-assist pads above the fullscreen kiosk window ([`4f1313a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f1313a1136ead01843eccc0fe7d78f788aca1c1))
- **portable**: show touch tooltips at release, long-press fallback ([`476150f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/476150f604d1eca1f17762be8df660eaa50f82a1))
- **portable**: arm long-press only on the deepest press receiver ([`64b83e3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/64b83e3ef8bfe929448094e4d21a2d4f6b9e4df5))

### Chore

- **app**: bring the touch-assist pads ruff-clean ([`403cb07`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/403cb0772d55396f631b47dd62a4211a0763a670))
- **device-viewer**: bring electrode_interaction_service.py ruff-clean ([`cd87f57`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cd87f577d1f128917e21cdab78883171bfafd4b6))
- **device-viewer**: bring auto_fit_graphics_view.py ruff-clean ([`0226b26`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0226b266e1215c9492750187c9623e6f06c5ad78))

## [v1.15.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.15.1) (2026-09-01)

### Fix

- **user_help_plugin**: degrade gracefully without QtWebEngine ([`3b21e60`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3b21e608ce5056d4202c38c4d243936db3eb0209))
- **protocol-tree**: collapse timeline in idle phase nav ([`8c49d54`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8c49d5436e07e6dd7e4dbadc9d330a4498543563))

### Chore

- **user_help_plugin**: bring menus.py ruff-clean ([`4dbfedf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4dbfedf8e8f0a36b77ba2eb180ecb528cf3cb1d8))
- **protocol-tree**: bring dock_pane.py ruff-clean ([`b522bf5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b522bf55df4e88a8cfe4074feb834bc7efc5c7e2))

## [v1.15.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.15.0) (2026-09-01)

### Feat

- **portable**: kiosk fullscreen on the rig ([`c7e565c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c7e565cd99a8a8402708267a3a5ab60fa1438f0e))
- **portable**: finger-sized dock separators on the touchscreen ([`5b43f45`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5b43f456dc1fdc8465f26a0c1a06e078966267af))
- **portable**: apply Display Scale via explicit Apply/Reset buttons ([`4a9406b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4a9406b952a709e3dc684f5af3d7b2a4192f4bbf))
- **portable**: live Display Scale through the display server ([`8f50f67`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8f50f67e077ac3ec76dbaf88343686b52fc64656))
- **ui**: preview the chosen scale inside the Display Scale dialog ([`2e01248`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e01248feb19c8e29a56ad05efcd67775dd3f8c5))
- **ui**: add an app-wide Display Scale slider ([`c360342`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c360342b2c1c70ef19a11ecf0ddb47cf4172b8e8))

### Fix

- **dropbot**: shut the monitor scheduler down on plugin stop ([`3df7cd0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3df7cd00c4be45201e50075f71207635d2e2d9cc))
- **portable**: shut the monitor scheduler down on plugin stop ([`e2e27cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e2e27cb058479b4c316dd369f681d650276e57e6))
- **perf**: stop SDL audio probing from stalling boot ~30 s ([`b4fdebc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4fdebcbabca7d3f36d08396a493e7240e411ea4))
- **ui**: resolve the task from the action event ([`284817f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/284817f459996cc38b41d29977164127efacf877))

### Refactor

- **ui**: retire the app-wide display scale integration ([`e45da3c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e45da3c2f931dee82cef5a02d7a16e5781671d0f))

### Docs

- correct the SDL audio stall comment to the verified cause ([`052f1c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/052f1c187f6847f5523f6846409efc77c4eafdcd))
- require a closing keyword when a PR references an issue ([`5a4299a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5a4299a4f33ba6cf251b869f986ac443ed7a0eb3))
- require issue metadata to be set via the GitHub API ([`7164700`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7164700b8ae95777a221bd1e3f8e9938b44f5711))
- declare validated publishing default and name style exemplars ([`f5ea59a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f5ea59adcba89d636a45d5c32e5462fbcc299c6b))
- make AGENTS.md the single source of truth for conventions ([`fb9a2d5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fb9a2d50f722d22de6a7352e8558b58a5e3a4792))
- **agents**: codify TraitsUI-first views and pyface.qt imports ([`d1920df`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d1920dfa549739dcda7f2d4b752112200744e846))
- label import sections with comment headers ([`6ca5f40`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6ca5f40f7238873596737d6e33182b1bd07f277d))
- add AGENTS.md agent and contributor guide ([`7b02583`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b025836de56a19058409e6c3095447568450449))

### CI

- enforce the copyright header via ruff CPY001 ([`42a28c2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/42a28c2325010d642b555a04e815f02fb15ba47b))
- adopt ruff for formatting, linting, and import order ([`b5cd12f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b5cd12f441c858cb0a1fadde21d90dcae80ef805))

### Chore

- **style**: ruff-format the runner, task and preferences ([`b315db6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b315db6377102b04a52e260a4d7a093d673b4526))
- stamp the AGPL copyright header on all Python files ([`4e82f77`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e82f77e31584192a6eddf00705ef8b7cccffdb7))
- keep agent working plans out of the public repo ([`b1bcf33`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b1bcf33631d893a38d035076b4a553b6818d7ece))

## [v1.14.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.14.0) (2026-08-27)

### Feat

- **portable**: use MDI magnet glyphs for the magnet toggle ([`7110023`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7110023d76b65f00ef0590e12b62030957046719))
- **examples**: add MDI icon-buttons TraitsUI demo ([`c00c44d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c00c44d9b1f5c666ae91ec5dba8177e005be3954))
- **utils**: allow a custom icon-font family on glyph editors ([`bf9957e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bf9957e93944e854904ea0e847122e2947d9dce1))
- **style**: ship the Pictogrammers Material Design Icons webfont ([`4223056`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4223056d3059a3ac519a481028b22b7ff8ea97b8))
- **portable_dropbot_ui**: single-column status pane, connect row advanced-only ([`a6ea674`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a6ea67462a7169cb766927526728f25101d70617))
- **microdrop_utils**: log source checkout version at startup ([`0115fbf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0115fbf476cc0f9525b1ddbda726fdc67dec3437))
- **portable_dropbot**: tie HV master enable to realtime mode ([`07179cc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/07179cc330d628704a2272d3c31dbf8fa3892841))
- **portable_dropbot_ui**: mechanism glyph toolbar in status pane ([`c830564`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c830564fb930946deb616f95022561c01ed2eb31))
- **style**: toolbar glyphs and adjustable status-icon size ([`414540b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/414540b3627aca7b8aaac0e2d893683f8c8c3393))
- **portable_dropbot**: outcome-aware logging in all request handlers ([`f4a1430`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f4a1430e3713b9d8d8b920f81e0a08310f9425cd))
- **portable_dropbot_driver**: log every command and its outcome ([`87530c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/87530c100fe22996cf4cdd3a77046bdebbf24873))
- **portable_dropbot_ui**: vendor-parity panes + grouped status pane ([`def11fa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/def11fa7c5da37473e70ac3688c83159054ceded))
- **portable_dropbot**: calibration, temp, PMT and system services ([`5f6504c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5f6504c5f15d6b45d28fadd885f753274f0ba204))
- **portable_dropbot**: vendor ML-calibration driver commands ([`f8efa47`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f8efa474ccef1f8dac638aabb7a5dad199d7a88b))
- **portable_dropbot**: disconnect toggle + pane control polish ([`5c0c4f8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5c0c4f8144c05f05f77d1e4c8e44a399ae5ad562))
- **portable_dropbot**: light control drives the fluorescence LED ([`19241c3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/19241c3731fb7bef43a338d56b8b4648e46dc7f4))
- **portable_dropbot**: lighting controls + illumination wire fix ([`ee5232c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ee5232c7ddd1cc854c59a46c7e93f3f887c7f9df))
- **portable_dropbot_status_and_controls**: touch-friendly move spins ([`814b767`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/814b7679750763e4e3227d6b0c2001f076655efd))
- **portable_dropbot_status_and_controls**: vendor-style motor panel ([`8d966da`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8d966dae7812d65558a1fe7f69978ffbbb5f1f0c))
- **portable_dropbot_status_and_controls**: DropBot-style status pane ([`d1da70e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d1da70ed6da2e6c75b183e6b86e8fefef231c3eb))
- **microdrop_utils**: opt-in clickable status icon ([`0cc2bba`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0cc2bba5c0ec117882dcc25caa972f05d735c879))
- **portable_dropbot_controller**: explicit COM-port connect service ([`b43859d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b43859dbd8a4286393fb4eea660c9217f3ced6c4))
- **portable-dropbot**: smoke-test script; fix driver-API mismatches ([`98e2084`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/98e2084980d55020e463a4e83efe52cee55b5a9e))
- **portable-dropbot**: chip lock and light-intensity control ([`cdb2ceb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cdb2ceb0fc5dd6b502fd90d7b8fc78a917aac126))
- **portable-dropbot**: vendor the bare-minimum driver ([`d5a4164`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d5a4164009bab70698fe015b2828168340f9da1b))
- **portable-dropbot**: --device portable plugin wiring ([`2752452`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/27524527c8656ef762ace033e4877b4c3c64d1fe))
- **portable-dropbot**: status pane and motor panel ([`2651319`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2651319164913aa3f035a9b51e39f934c5a2f474))
- **portable-dropbot**: publish status in engineering units ([`8bb1542`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8bb15426a8dad13708e090001e6d488278f92cf0))
- **portable-dropbot**: backend controller package ([`56a3cdb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56a3cdb2017a4b4bd97901b6d11bef8c01b12c0b))

### Fix

- **style**: fake the windows11 drop shadow on Fusion icon toggles ([`df33d1f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/df33d1f27984180e6e44163462b54a9a17f16711))
- **style**: accent-colored checked icon toggles under Fusion ([`abb0477`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/abb04775bb37948b8ffe7dc669766f43e061b448))
- **portable**: put enabled/visible conditions on items, not groups ([`818921f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/818921f73d8de4cc8ab75fda27183d51620ceee9))
- **portable_dropbot_ui**: even minimal spacing and trending magnet glyphs ([`f1847b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f1847b8e30a92ce1d0052e1d0f96edf9dc6f033e))
- **portable_dropbot_ui**: render mechanism on-states popped out, off sunken ([`4fbb6ca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4fbb6ca503cdfcc32a45b695244142416ad79826))
- **application**: scale splash screen to fit small displays ([`f0a4edc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f0a4edc798bfaed783eb1e2fa2b171b5ecf5986b))
- **portable_dropbot_ui**: grey the voltage readback when HV is off ([`d4ddf71`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d4ddf715d7b69f35357b64c923f0270d3aa9c0c9))
- **portable_dropbot_ui**: icons show state, not the click action ([`119c39c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/119c39c4dcabf08c93397fda07f0ae918a8ad9ee))
- **portable_dropbot_ui**: scale light readback from raw 16-bit ([`4e4fb4c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e4fb4c8dbf9a3c44292191aedcd075ee1b9982d))
- **portable_dropbot**: log buzzer/fan request outcomes ([`8aa0f3f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8aa0f3fb2cb1ee03934570de182a35220c7af3c0))
- **portable_dropbot**: gate actuations on realtime mode ([`5ea1497`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5ea1497ca020013a401dafaced864857f5469129))
- **portable_dropbot_controller**: tray toggle reads motor STATUS ([`56b1494`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56b1494566b97ec100d7671c1f05bcc6686dceff))
- **portable_dropbot_driver**: patch vendored driver for field bugs ([`3251584`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32515844bb2de35b0a51dc211b5f1b9a0b662484))
- **portable-dropbot**: a port that merely opens is not a connection ([`c761f65`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c761f65d0807713d7a02f387efe5a3cbbc461f99))
- **portable-dropbot**: declare the link lost when status goes silent ([`98f8605`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/98f86059c6d62b3dc15452e7a0b38b82a74ffb76))
- **portable-dropbot**: one status-bar icon, not two ([`25abb53`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/25abb53b501b8228a035ae4655b635e6dda78eb2))
- **portable-dropbot**: fast, non-overlapping port probes ([`6c7f4d6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6c7f4d6168a9669fc102c954c10b86350787945b))

### Refactor

- **style**: route font loading through one font-file registry ([`a68a9a1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a68a9a1159c3ace39b33cc37c17776e3dcea1234))
- **portable_dropbot_ui**: consolidate panes into More/Advanced ([`74018e3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74018e35b0d26bdfa245b293e4d090611dc53cfd))
- **portable_dropbot_ui**: split package into MVC folders ([`73606d2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/73606d2ee0658666d367c79417f09189e4494ae2))
- **power_system_ui**: replace on/off buttons with bool toggles ([`c9e2a3e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9e2a3e571e11eaa012da2e695bcbe0ed51eb386))

### Perf

- **portable_dropbot**: skip the status tick while a driver call runs ([`dee298d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dee298d02fc58b22facf12cc7b912f13985a4e3f))
- **portable_dropbot**: stop polling motor positions every tick ([`dac5456`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dac5456578658327f04396633c624b8d74853de5))

### Docs

- spec for the Portable Dropbot device type ([`d16fdd7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d16fdd7353fee8c71c94fef92f83d1e7c856add9))

### Chore

- **hooks**: raise large-file limit to admit icon webfonts ([`070d511`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/070d5114d056a154202d18ca920250654d231a74))

## [v1.13.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.13.1) (2026-08-27)

### Fix

- **utils**: make ColorColumn cells editable via the trait's own editor ([`9325a60`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9325a60714aa0a6ead84d5c96bd08c6675fd5885))

## [v1.13.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.13.0) (2026-08-25)

### Feat

- **plugin_management**: hot-load Update All updates ([`d7c37a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d7c37a4b2f33d9a21f5d8e02c3da6d1ab33746e1))

### Fix

- **peripheral-base**: free listener actor on plugin stop ([`ce8ebaf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ce8ebaf8f91c4bb3d43b0c988f40fcae90fabef6))

## [v1.12.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.12.1) (2026-08-25)

### Fix

- **firmware-dialog**: tolerate a missing preferences helper ([`97b55f6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97b55f6f629921dccca01639557088c7c300be08))

### Refactor

- **firmware-dialog**: parametrize panel view and intro text ([`7709427`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/770942732472f07c578f78b89b681184854511d9))
- **peripherals**: extract flash step into overridable hook ([`7e9716c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7e9716cdc6d3d99e07c8a9c94c3fdb94dd8e33f5))

## [v1.12.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.12.0) (2026-08-21)

### Feat

- **device_viewer**: corner-marker size in the sidebar ([`fcc9d2f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fcc9d2f9028f0a5277e63af911b2b6d2e5646dac))
- **device_viewer**: per-pane toggle to show all snappable corners ([`ff027c4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff027c4ff728e9d783140fc89e4a01de1f3ede60))
- **device_viewer**: corner-marker color and alpha in the sidebar ([`3849faa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3849faa1f6ba72a7ecd95b6853794cfac9f72f76))
- **device_viewer**: view-all-corners markers in QuadOverlay ([`71e3c04`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/71e3c0413569cc9f8a61e00203a4ea5678b28a64))
- **device_viewer**: default snap radius to 100 px ([`275cbfc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/275cbfc1af4edd1b12f101dcd0fb5c856809ccdc))
- **device_viewer**: expose the SVG-to-scene path scale ([`5c831c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5c831c1973e8444eed3d5a6374755cd222ead7bb))
- **device_viewer**: combined Camera Alignment dialog ([`09389c5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/09389c5a57b95b92d1101177cbe7795773eb3ad2))
- **device_viewer**: endpoint and outline panes as TraitsUI MVC ([`c9c9844`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9c9844d37958133e67d56b944d4921e618e536f))
- **device_viewer**: alignment settings sidebar as TraitsUI MVC ([`b33ca89`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b33ca892739e712254afedd84a80560ed64f2bb1))
- **device_viewer**: persist camera-alignment prefs ([`77b84cc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/77b84cc743b8c68d3ae36e5f3b72be2ff435812b))
- **device_viewer**: zoomable pan canvas for the alignment panes ([`a3ae66c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3ae66c14e4981cb6c5b693c82825d43fabd523b))
- **device_viewer**: Shi-Tomasi corner detection helper ([`0da0a6d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0da0a6d1e54fe4f148b9d5df634a87613caab9c0))
- **device_viewer**: parametrize QuadOverlay style and snapping ([`0d23b5a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0d23b5a1224144916391e3d59233cd1f12f36b81))
- **device_viewer**: add camera-alignment constants ([`f2e8570`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f2e85708043a7642e62d4b07bd507c085d7c9188))
- **style**: add TEXT_BUTTON_STYLE for real-word buttons ([`7b6fd08`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b6fd08846f05e253e71a55a8cd0385935c3c318))
- **style**: add the photo-camera glyph constant ([`f322aa3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f322aa34232c8272484d5b62210a527d5b4f22ee))
- **microdrop_utils**: add hex/rgb color converters ([`c1bbcd8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1bbcd87aefa3ea5775f981c0bf0268f285d9540))
- **device_viewer**: manual per-device camera-alignment endpoints ([`d0f3aee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d0f3aeee7b739246448c65d40e9cf0ab302f68dc))

### Refactor

- **device_viewer**: outline pane left, endpoint pane right ([`6352bf3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6352bf358fdbd43294f6506172b8ff10707ae280))
- **device_viewer**: alignment buttons join the Camera Controls box ([`303ccf2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/303ccf2b85422b76a82a30fc573c417e31067e6a))
- **device_viewer**: one shared alignment snap radius ([`d4c2784`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d4c2784660fdd44dacaa9613c9a4cc4c9510c4c2))
- **device_viewer**: drop the alignment dialog's Close button ([`6fc427f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6fc427f9598cb31abd4e7a15a9054266fa360fa4))
- **device_viewer**: declare alignment observers with @observe ([`0b1acc6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0b1acc605c276cacb2f3317331dcff750e977013))
- **device_viewer**: sidebar opens the combined alignment dialog ([`fcab2a5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fcab2a56a41668466b4b38758981342a89da6139))

### Docs

- **examples**: standalone Camera Alignment dialog demo ([`648d247`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/648d2474a970ac5d8c061065a75a5c54eba25ab2))

### Style

- **device_viewer**: rename sidebar button to Camera Alignment Helper ([`cabebd9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cabebd906486e6db4225603dbbb9251c86aa5558))
- **device_viewer**: breathing room under the alignment buttons ([`6103ba2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6103ba20102ff8bb24430417a5f1ad2578592503))

## [v1.11.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.11.1) (2026-08-14)

### Fix

- **ssh-controls**: upload errors reach the dialog ([`b617841`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b6178417871fb8c736c87de30382eb380252c8e4))
- **ssh-controls-ui**: survive menu rebuilds with one portal session ([`65efa7f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/65efa7f1c49b8e1e295a160b8048545cdc8e7c59))

## [v1.11.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.11.0) (2026-08-14)

### Feat

- **touch-assist**: keyboard modifiers, arrow auto-repeat, key colors ([`a6e5d0d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a6e5d0d2058ecfd3289fff2be29837c445e73be4))
- **touch-assist**: hold latch on the virtual mouse ([`e8cfe85`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8cfe85926845dbfe9c5e9a2d733668b261457b9))
- **touch-assist**: the virtual mouse ([`c9c9dc9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9c9dc93a98f70ecaa54ffaa3f5ac88261c67264))
- **touch-assist**: virtual numpad and keyboard pads ([`1d65d94`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1d65d94144390f6b5e2a00a98a2fd95a0f36c1b1))
- **touch-assist**: Tools menu group and widget manager ([`a89abe9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a89abe9a403a776b804456a0cec12174be05c9ca))

### Docs

- spec for the Touch Assist tools ([`ff0b04c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff0b04cc97507c858e7488c76cef8b0600834e8c))

### Chore

- **preferences**: quieten startup logs, name the default svg ([`19439af`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/19439afdfb4de9d7a53c812d136cdd8030c765ca))

## [v1.10.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.10.0) (2026-08-10)

### Feat

- **protocol logging**: validated publishers for the contribution topics ([`1d88f19`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1d88f19197040374ea1dd09c5897428aa07f5eb8))
- **protocol logging**: route contribution topics to the active logger ([`cb15ab3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cb15ab3c73b12bd3723568c7a7a2ef2548b1261a))
- **protocol logging**: accept externally contributed metadata + data rows ([`6de2693`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6de269328400d4f37b9042de4ba1dc25889cff51))
- **protocol logging**: add report-contribution topics for external plugins ([`e9ba75a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e9ba75a14123fea0c29fdbbaebd95c549eb34f9f))
- **style**: add glyphs for the rolling-ball controls ([`78bb00a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/78bb00aabec8dda8a71cd58a91168bac2c3e289f))
- **traitsui**: add a mode-aware icon button editor ([`20478e2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/20478e2fc26682d4b9a4fdf30e9cb0cdca8503a0))
- **style**: add copy and paste glyphs ([`7b39d0c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b39d0c1bcab1aac23f5a73ff29ca8414ef7e47f))
- **dropbot_consts**: add kapton to dielectric constants ([`f55946c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f55946cb0ec346f3f4cc6912273e9fa90fc5fda2))
- **icons**: add the scale-calibration ruler glyph ([`acbd883`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/acbd8831847db965c798f7b0079842c46cfde28a))
- **icons**: add the contour ROI glyph ([`721aaa1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/721aaa13339114cd2bbca17ae679e1b49d115e3f))
- **icons**: add the capsule ROI glyph ([`a1b7856`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a1b7856d1d0561e142688badfa4ae48431cd960d))
- **style**: add function icon for fit equations ([`2096da5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2096da552f0ebef38294c51be508b4985b524254))
- **style**: add chevron sidebar-toggle icon constants ([`90244f8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/90244f805b585339190bbd3769559f71ebe1ae55))
- **icons**: add ROI analysis glyphs ([`16348a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/16348a4adb6111a97531081c8b243eb0dd572156))

### Fix

- **traits_editors**: Sliding toggle editor needs on/off defaults. Now its True / False. ([`37a93de`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/37a93de18d182595eb983acc36e14cb10164847a))
- **setup**: keep the git self-update out of worker processes ([`cf2d609`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cf2d60985844696b3741edc8a43e08d976f395ed))
- **utils**: apply the Item tooltip to an in-place toggle ([`d2f2585`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d2f2585dffd99f482df9b24552b5ee1127695e50))
- **utils**: grey out a disabled in-place toggle ([`03b8734`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/03b8734c5efd13279fa996ee16a16744d65afb0f))

### Refactor

- **traitsui**: overridable stylesheet for the in-place toggle ([`82e39f7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/82e39f743f2c174dba8522ca439915cde52ca3ef))

### Docs

- point demo + MESSAGES.md at the validated contribution publishers ([`46a6c5f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/46a6c5f8adfcfe4237a60a4209c4161cf33ae40a))
- **demos**: headless demo for protocol-report contribution topics ([`6ba2af2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6ba2af2560ebb4923314f982108b7897dfb3c532))
- **messages**: detail the protocol-tree run-logging flow + contribution topics ([`2ce2c41`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2ce2c41d3b293fe991b0e427af13249e0a82da21))

### Test

- **protocol logging**: cover contribution message contracts + publishers ([`7d94813`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7d94813045ebaad120db4d1e25ca639e83f379fa))
- **protocol logging**: cover contribution topics end to end ([`db9f7fb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/db9f7fb94b9820139d19dc5046ff672aea8eca96))

## [v1.9.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.9.0) (2026-08-06)

### Feat

- **peripheral-base**: resolve shared VID:PID ports by device id ([`cf1f4d9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cf1f4d907cae0347c4d28cf2266d4f6074bb1283))
- **dropbot consts**: Add kapton to dielectric constants ([`9e50eb7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9e50eb7758f4431c8fa9cc039795ff2881472647))

### Fix

- **peripheral-base**: pass the claimed port handle to the proxy ([`9fe547d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9fe547dd417634ba9a46fd464f5e9ae16cc49341))
- **microdrop_utils**: keep identified port open, hand it to the claimer ([`fcf051c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fcf051c5b9579425551637964a2cc0397fed782f))
- **microdrop_utils**: harden whoami probe against missed replies ([`83c309b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/83c309bc50b87aa85ac8ef63acc5f3a2b65f514c))

## [v1.8.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.8.0) (2026-07-30)

### Feat

- **protocol-tree**: idle phase-nav checkbox, buttons, timeline (#493) ([`afe223a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/afe223a4c76a14e86cf8501d44a9e7cbc98e1fc5))
- **protocol-tree**: subscribe to phase-navigation topics (#493) ([`b4b5e48`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4b5e48d137debee39ecdbdc3116a2be5fd514f0))
- **device-viewer**: sidebar phase-nav checkbox and idle actuation gate (#493) ([`af5b49a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af5b49aca2a9c8ae92bd4078c6e6d1ebf3d3d223))
- **device-viewer**: idle phase stepping in RouteExecutionService (#493) ([`4aa0ef4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4aa0ef41e0cbb5311a92380d4175631361d98a02))
- **device-viewer**: phase-navigation topics and synced mode trait (#493) ([`eb688c7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eb688c7c36976f68c0595f5cc0e119965e8d3d93))

### Fix

- **phase-nav**: harden idle phase navigation after branch review (#493) ([`d01fff6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d01fff6092d810dfe4603dac7d6e2c65a5a956a1))
- **protocol-tree**: resync idle phase-nav buttons on run-state change (#493) ([`972c763`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/972c7638d678df8e0c20e3a627c86356347a489c))
- **device-viewer**: guard phase-navigation request content, not just JSON syntax (#493) ([`56b65cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56b65cfb787251f17e9a1d8f6e5f56608bcf2807))
- **device-viewer**: stop navigated-flag leak and toggle loss in idle phase nav (#493) ([`081051f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/081051fc6968cd1d87399e053fb41b90751356ed))

### Docs

- record phase-0 rebuild decision in idle phase-nav spec (#493) ([`cd3b7d8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cd3b7d83012fd93d89a75500ecbfc865a96b5219))
- document phase-navigation topics (#493) ([`95f7a39`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/95f7a39b2c9761464d9ce46ed78af0752e9a3990))
- add idle phase navigation implementation plan (#493) ([`bc95d02`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc95d02e0bdb44149e518974d7c4d6882ec6afce))
- add idle phase navigation design spec (#493) ([`ab1c5d6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ab1c5d6be73f072360dd7ac3f7eb6e181cf61970))

## [v1.7.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.7.0) (2026-07-29)

### Feat

- remember the legacy import dialog's last selection ([`3a3ef04`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3a3ef048928d28027038b4791204210d8f8fb770))

### Fix

- size dialogs by rendered text, not raw markup ([`01181fa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/01181fa80671968462a21a8ecd239ffd23afddf1))
- let callers override disable_main_scrolling ([`bc4f8b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc4f8b0e60d638b887d5071dcdf5156d44e52bba))

## [v1.6.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.6.0) (2026-07-29)

### Feat

- ask before renaming a colliding device import ([`1ddd00c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1ddd00c0d8d0f769581b1cdd6a7b19c336280779))
- save imported protocol and device into repos ([`370c517`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/370c517f6ef61726cf5aadc16b314b9fa0c8aac7))
- add Import Legacy Protocol menu action ([`0492cee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0492cee97cdd2e135d9a0bd45200aa7cb1f5e0b2))
- add device SVG load request topic ([`c194b69`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c194b6957a2208162e4daccd4010ce66a55867b3))
- build protocol payload from converted steps ([`b17f760`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b17f760cc124e249c520d2c65fad6c5044e0cb39))
- map legacy protocol steps to column values ([`d65cae3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d65cae36cd63e21158770bef24dbc976cb19149c))
- add legacy conversion report model ([`49d79c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/49d79c12732c174206496a4cbcf4529cc36cab59))
- scan legacy MicroDrop device folders ([`44f7861`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/44f78611186478380b1c28fefb2a160100be082b))
- map device SVG electrodes to channels ([`020e948`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/020e9489b597308096f26267a6ccac82108b6f2a))
- read Python 2 MicroDrop protocol pickles ([`875fc13`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/875fc131ac416140bf8c2ce1b193c81a562d4e20))

### Fix

- prompt reliably on imported-device mismatch ([`a545f19`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a545f1955ec06973716b0e06b6b210010b45cad3))
- probe legacy protocol files structurally, not by unpickling ([`13fecd7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/13fecd769c5b48645a125102098b484e20fa01ec))
- address final review gate on legacy protocol import ([`1920ede`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1920edee8981af8de4d1f8e0e58e8fccde03a568))
- resolve legacy import path traits without relying on notify ([`bbe1e51`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bbe1e51ca5a7412d2db64e5b81c6257124bb8ab8))
- guard os.listdir against unreadable device dirs ([`1bda007`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1bda00779d9eb204139dd1a15fccabb224bbe3f5))

### Refactor

- style device mismatch dialog like conflict one ([`c5fba8a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c5fba8abc055eccacc09c01b03db48fd568560d8))
- polish device name conflict dialog ([`a5424df`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a5424df58dd146ba3a01cfe161ef09e3d71540f8))

### Docs

- fix SVG iteration in the import plan ([`cb2a411`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cb2a4113922abc137fe168019c43a7bb371c97c3))
- cut test scope for legacy import plan ([`f28a5ff`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f28a5ffaefde75fc5862d3d767fb255c0c8e541f))
- add implementation plan for legacy import (#438) ([`97bef31`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97bef3160769952caa139a4a6e0fa2ab7701d686))
- add design for legacy protocol import (#438) ([`a12fa8b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a12fa8bebb7a925577350e3e8306a0adb62f9064))

## [v1.5.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.5.0) (2026-07-27)

### Feat

- **microdrop-utils**: draggable width grip for table row headers ([`ddb461e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ddb461eaeea178fe1257b80f9505887c279e1d17))
- **protocol-tree**: wire up the Run Selected action ([`11cfc44`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/11cfc4435e53403a78c7ec7280395c47691ed47a))
- **protocol-tree**: add Run Selected Steps to the tree ([`a7a10b7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a7a10b7e42dae2f4a00a87ecd5fc806428667c8d))
- **protocol-tree**: scope status counts to the run ([`b318f98`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b318f981adb348eb3ac274bb7531f5d8250c0790))
- **protocol-tree**: add a run scope to the executor ([`ee1c326`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ee1c3269c757aa521b6daab7f04490690fb4ebbd))
- **protocol-tree**: scope frames to a selection ([`d56da25`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d56da254b058bc4797ff082836041c923942dff0))

### Fix

- **device_viewer**: make route table spacing user-resizable ([`2f92cb4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2f92cb45ee563b9ee06bd020cbe351781cd68924))

### Docs

- **protocol-tree**: add the run-selected design spec ([`0d7a6ad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0d7a6ad770edcf8d5d26020c2dbe278f33a2d17f))

## [v1.4.3](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.4.3) (2026-07-24)

### Fix

- **examples**: update imports for relocated demo packages ([`f8eb547`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f8eb54712841aae9a52f8d196184b37363e9412a))

### Refactor

- **examples**: group demos and style examples into subdirs ([`0d40814`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0d408144875cc7a5b8de86681af2205ec5cbd115))

### Docs

- **readme**: refine what-is-microdrop intro ([`825f170`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/825f1706db72fded2855a42ab7c2def778f8b0f4))
- **readme**: add application screenshot ([`b9f1589`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b9f1589aea8a43bf04f9ca025c6068cef9d4e3f4))
- **readme**: point launcher section at microdrop-launcher repo ([`58cb27f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/58cb27f7a04e7771cea310d1c67970bf16442a13))
- **readme**: rewrite README as user-facing front page ([`a4b012c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a4b012ce84a62de5808af203b0248e6ff84ea2a3))
- archive pre-dev research to docs/DESIGN_HISTORY.md ([`a92e2e0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a92e2e0688945e93edf903109278437012280f3b))

## [v1.4.2](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.4.2) (2026-07-23)

### Refactor

- **firmware-upload**: drop the dead default_firmware_dir trait ([`23b3853`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/23b385332164d89d8ac27406aa2e0b8f3dbeef0b))

## [v1.4.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.4.1) (2026-07-23)

### Fix

- **firmware-upload**: persist firmware source in prefs ([`a3976b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3976b89d01a1a8fb0c0b7585ebba03332d38313))

## [v1.4.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.4.0) (2026-07-22)

### Feat

- **microdrop-utils**: shared firmware-upload dialog view ([`f42cbd6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f42cbd6b6239baf76b9b479b896e1626beffa979))
- **peripheral-base**: shared firmware-upload backend ([`12eb79c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/12eb79c0fe9f715bb8c659d92f86e8c614e63207))
- **style**: add ICON_ARCHIVE glyph ([`8f6c461`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8f6c461ae7e09336a4299bed4e485e2c23d39af0))
- **style**: add ICON_USB glyph ([`2775836`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2775836d365b8bdbbb8364b2f11cb4059129e2ab))

### Fix

- **uploader**: unwrap the firmware folder past macOS zip junk ([`d085a5d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d085a5de8d086676d3a41a0f4bca3f2641ef5131))
- **peripheral-base**: rebuild the monitor after it was shut down ([`d9027f7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d9027f76cc3b46cfb8de34436378863134ef7cad))
- **peripheral-base**: don't resume a stopped monitor on retry ([`b67725f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b67725fc664d8830fb4f7fd72e29a68aaba28b9c))

## [v1.3.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.3.1) (2026-07-21)

### Refactor

- **microdrop_utils**: use QToolButton for glyph editors ([`53d32e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/53d32e8d4db16fab14788805a7bf17f78712c120))
- **device_viewer**: drop the raw-frame capture path ([`bb18a3f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bb18a3f8972efddc9cc0f15acbc8a8adf51b22c9))

### CI

- state-based release detection — merge-method-proof, recursion-free ([`4f8f58f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f8f58f8981d92e5c68520d7f992ad22d52f9bb4))

## [v1.3.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.3.0) (2026-07-21)

### Feat

- **user_help_plugin**: prefer GitHub-styled markdown render, offline fallback ([`e333b11`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e333b11c0a6cd7e2bf45c0d951e577035fa0cbcd))
- **microdrop_utils**: GitHub-styled markdown page render with shared tag-token escaping ([`6d298cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d298cf192461290ae63ac561466f5857e75e15e))
- **examples**: mock-changelog render demo for What's New + Changelog viewer ([`6d20b29`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d20b29245f0bf46247dec4e4a71cad9fc93a17d))
- **user_help_plugin**: Changelog help menu item rendering CHANGELOG.md ([`12e2285`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/12e2285df8a39e02c45a978eaad79a5976e50828))
- **microdrop_utils**: markdown_text_to_html QTextDocument helper ([`2e1a286`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e1a2863305ea3541deae021eef8936c3c350657))
- **microdrop_application**: What's New startup dialog for new changelog sections ([`0161cab`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0161cab6832d4ca118a5d473b76fe911ea104c44))
- **microdrop_application**: CHANGELOG_PATH constant ([`75a51ad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/75a51ad93a34ee91049bd0ebbf8c058800152a96))
- **microdrop_utils**: changelog delta helper for prepend-style changelogs ([`40b49bc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/40b49bccc2a5bde7d590d8e61811967e6dd788e5))
- **user_help_plugin**: move Download MicroDrop Launcher into its own bottom menu group ([`db0193c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/db0193c78c91cea7c5ff38e3a0c50fea1bb518c7))
- **user_help_plugin**: show only the rendered launcher README in the help dialog ([`53e7e29`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/53e7e29a4839a7c56dd795543d60680a4c9982c9))
- **microdrop_application**: WebViewDialog accepts html_content for direct HTML rendering ([`c3698a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c3698a472e6f8906d23b2f44ab75ab27d5f726ff))
- **microdrop_utils**: add helper rendering GitHub markdown files to standalone HTML ([`f38aec9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f38aec9fe374812f3c7c7bce7e80433c46df4492))
- **user_help_plugin**: add Download MicroDrop Launcher help menu item ([`9ea0860`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9ea08605eb4a5609e690caabbcdef6f4dec7be22))
- **user_help_plugin**: add architecture html path and launcher README url constants ([`4f1a4d4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f1a4d44e0487e1a33ec84c10d4209803ceab84e))
- **microdrop_application**: add generic WebViewDialog for HTML/web content ([`a770691`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a77069152ea826b99ae786baf45a92bb6b672bf4))
- **pluggable_protocol_tree**: on_row_loaded column hook after load ([`4fbf9d3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4fbf9d3d40c529648f3b311ac50cc3c49e4db6e5))
- **pluggable_protocol_tree**: handle add-step requests, identify groups ([`703ba3c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/703ba3c7e3696cab3c8bfd4e730f2833f0189afc))
- **pluggable_protocol_tree**: add-step topic + group id on row_selected ([`84787dc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/84787dc34d1be720713953b311a4753ceec026ce))
- **pluggable_protocol_tree**: route reps lock honors mode dialog ([`5758282`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5758282c215ece9c204ffad2bbb6a46ebb303223))
- **pluggable_protocol_tree**: bulk set skips locked cells ([`b0a06b6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b0a06b69a5f038a91fde97dfa830b0db4fed940d))
- **pluggable_protocol_tree**: enforce column locks in MvcTreeModel ([`fa7df3e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fa7df3e51c0c7d9fe0bc0eaed35bb1ea5a2c3fb9))
- **pluggable_protocol_tree**: owner-keyed column locks on BaseRow ([`3aac62d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3aac62de637299e037897af76d7bb817895be65d))
- **microdrop_application**: add choose() multi-choice dialog ([`e43c9fc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e43c9fc4f058d8feb3adbb22f75ee497723ceb8d))
- **microdrop_utils**: configurable dramatiq worker settings via json ([`bd983d6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bd983d673dfe0a0e0bfdba6a633229f5d959e13e))
- **microdrop_utils**: self-update source repo at launch ([`c1ac220`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1ac220d532e4cee2b8202cf104e84061972aaec))
- **plugin_management**: gate the upgrade glyph ([`b84e4a5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b84e4a5c173e49e8a13e2ae821fb227b78ba60ed))
- **plugin_management**: hot-load plugin reinstalls ([`94890a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/94890a2cb41542de790d9c7e41aea2e9f0e9fd08))
- **plugin_mgmt**: hot-load installs, skip relaunch ([`0c3a5c3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0c3a5c3667a3abc0b8da7ae97dd455bfea8f1021))
- **plugin_management**: add hot-load gate ([`5116545`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5116545d91ece2ed42186681a77314aa66f63d7d))
- **plugin_management**: compute requires_relaunch from diff ([`b122b29`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b122b295ed40a4c8e65198dea475338fba7396d3))
- **plugin_management**: add pixi env snapshot and diff ([`155159b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/155159b7c5739597c73cc188600decc00f83851c))
- **microdrop_utils**: mark enum cells with a chevron ([`0781451`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0781451acb7fd1a0283291cff405ed97fbd18afb))
- **dropbot_controller**: add validated publisher for shorts detected ([`890b184`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/890b1844c6c5a2e3b56b7aa9dfffd5bccf81c089))
- **traitsui_qt_helpers**: draw real dropdown arrow on EnumSelectColumn cells ([`0d3c497`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0d3c497829e86d503c78f09bd59320e5eb0445e6))
- **plugin_management**: version picker + hide installed in Browse Plugins ([`8734491`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/873449197421fde6285a2e65eb578769fbe7a434))
- **plugin_management**: collapsible details + always-on version combos ([`70482a3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/70482a3f440f428d508ee6c2ece92ed0794b95a7))
- **traitsui_qt_helpers**: controller base + persistent-editor helpers ([`f8e1e6c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f8e1e6c8a3f59f2fe0328691d6b37724b849a444))
- **plugin_management**: per-row install/uninstall + refresh handler ([`a3fb9b9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3fb9b96f05ac69081d2cbb61c92cfb130cc842b))
- **plugin_management**: tabbed Manage Plugins with installed-packages table ([`9907a24`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9907a2465d4de1ccc6f16d69c689327deeecb5e9))
- **plugin_management**: installed-package rows + details model ([`55aee93`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55aee936a390924dded2d03cd92339612ce52176))
- **package_installer**: version-pinned install + upgrade helper ([`3f317d0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3f317d0f1fb4c8da8a788660da6240e42e26569d))

### Fix

- **microdrop_application**: re-enable What's New cache refresh ([`5715a68`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5715a68007d280f39cd3767f8857b22f8fb196ac))
- **microdrop_utils**: escape tag-like tokens before QTextDocument markdown render ([`2bfe62d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2bfe62d81b371135b4e8d568abb93538c5b87342))
- **dialogs**: open help-document links in the system browser ([`e2c84ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e2c84efce120c4caf8c029885f63d435580dbcdd))
- **pluggable_protocol_tree**: rebuild column load-state on add-step insert ([`2f692df`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2f692dff6af9f9050ec9c1105c13c016c23723e0))
- **video_protocol_controls**: repaint capture_at on capture toggle ([`d410108`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d410108bd7a3bade033e82eeff6c69c89ed4b1ca))
- **protocol_tree_sync**: track realtime mode state and gate actuation publishing correctly ([`eef6cf4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eef6cf4124e983ac3afc179a0b0d98e0c49da186))
- **dropbot_monitor**: harden connection handlers in monitor mixin service ([`6cc3d01`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6cc3d01d264f11888cf0974343b5c4647e967417))
- **dramatiq_dropbot_serial_proxy**: unify connect/disconnect monitor event wrappers ([`33f150d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/33f150db73d75f1ac2e2cd237953498e1a87247d))
- **device_viewer_sync**: Do not publish when realtime mode toggles on in free mode. ([`52de026`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/52de026e6124b2d324321789b5a8ec453ade0b1b))
- **device_viewer**: return to draw mode once a protocol ends ([`62ab009`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/62ab009255d858dec099bfe68e8bdd92a5379942))
- **plugin_management**: refresh details on change ([`84458d8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/84458d8c32d3fd2cd83d4171e1c26eb1426d203d))
- **plugin_management**: stop swallowing uninstall errors ([`55dffaf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55dffafff0c7025592d6a66fcff779253da0c0f1))
- **plugin_management**: surface hot-load refusal reasons ([`69127d4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/69127d42cba26bd84dcb30f95582a1550d7daed1))
- **plugin_management**: drop installed rows after install ([`f6e3a31`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f6e3a31e7c1fefab83afa2b710c3671d7a9d2c77))
- **plugin_management**: snapshot modules before discovery ([`93a6675`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/93a6675bd40b0282c2c0d9dcf29091dc9df1b646))
- resolve final review issues in hot-load ([`23316cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/23316cfa004dda90b7f019cb112815f5c5dc08a1))
- **plugin_management**: relaunch via the microdrop task ([`5be1f24`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5be1f242e99c9381156a8a96797790d092dab0e9))
- **plugin_management**: sync env after pixi add/remove ([`a303f23`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a303f235b91ff1683d7a01b6e8353e4e06b3312b))
- **microdrop_application**: report no-shorts on a user-requested check ([`3a5fc44`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3a5fc44394ce51fceb48990bbc8af0da20f45c90))
- **microdrop_application**: make the suppress-no-shorts preference persist ([`16bd016`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/16bd016fbc287ab2a99bc5c9c85accf1747dee76))
- Revert "feat(traitsui_qt_helpers): draw real dropdown arrow on EnumSelectColumn cells" ([`d01500f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d01500fdec1196f0a4e51a86f2fba348cfb9b793))
- **plugin_management**: crash when changing version repeatedly ([`d0d375d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d0d375dd954a49baaa4a0aa58e571cc9f6534d30))
- **plugin_management**: version dropdown back to click-to-edit ([`a3ed064`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3ed064467ceaf3d54e21943a01b8939cc482096))
- **plugin_management**: version dropdown stuck after declining install ([`aaabe7c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aaabe7c6869f577eca7124a190f310f4739b013c))

### Refactor

- **user_help_plugin**: single OpenMarkdownDialogAction for local and remote markdown ([`9e35351`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9e35351d64a35f2478d9c68cb7acd2715aa3afde))
- **microdrop_utils**: fetch raw GitHub markdown; drop GitHub-API render pipeline ([`74c1526`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74c1526799539ebdfb42036e6d003f4a8f1e1490))
- **microdrop_application**: render What's New markdown via shared helper ([`bb928bc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bb928bc31079d2a9390e9a919f61b04615031143))
- **user_help_plugin**: replace About/Feedback dialog classes with generic WebViewDialog action ([`5cb9488`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5cb9488f5ed63a41478a14c38baa16fab981e0ea))
- **microdrop_application**: move WebViewDialog size defaults to dialogs consts ([`8921e42`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8921e423973568cd54fbf76598478174fa7545f1))
- **mock_dropbot**: publish/consume shorts via the validated model ([`fc56a11`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fc56a1189b980adf2f64421cee95163ead09d9f5))
- **dropbot_controller**: publish shorts via the validated publisher ([`252600b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/252600b4fdbd3090b12f66ccafbc10536df5b7be))
- **traitsui_qt_helpers**: add reusable table column types ([`ac26c2c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ac26c2c6c130aa0aa82d6551a11a44b58c98ca2a))

### Docs

- add ppt fluorescence-support-topics implementation plan ([`cd930b3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cd930b34d62eb8dae1730251b966a8673347637c))
- **pluggable_protocol_tree**: fix stale RepeatDurationHandler docstring ([`4f29a8f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f29a8fc8576f4c477edea6d4ba15742a5200250))
- add column-locks + choose-dialog implementation plan ([`4f7f090`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f7f090d83be19f5c0b66c53b86bead542815c31))
- **plugin_management**: allow smokes in hot-load plan ([`f22c816`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f22c816548a1da3d0c80aad4ef660425f118e9cb))
- **plugin_management**: plan hot-load implementation ([`c8f76b6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c8f76b61168472fabc87c81a7369f5c353e2db81))
- **plugin_management**: drop update-all from hot-load scope ([`6adcd9f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6adcd9fee4f298f3ddb025393973c3cbcac72ae0))
- **plugin_management**: spec hot-load without relaunch ([`96bffad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/96bffadb4f5d04ffd456df23605bfc0c46905796))
- **MESSAGES**: document the shorts detected payload contract ([`687faf9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/687faf99492e2ac44082fa3887a944d2e3dcc587))
- **examples**: reuse real view/controller in installed-packages demo ([`0ab0abd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0ab0abd254aa20e1166d0bf1f0361b14e33e5eed))
- **examples**: add installed-packages table demo runner ([`b9c201a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b9c201abceeaf8026fa084683493e29a07317f94))

### CI

- quote tag-and-release if expression — unquoted 'chore: release' breaks YAML ([`2beea35`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2beea3523c8d9ce79218ccaebeb54ef5cb80f4d5))
- changelog lists all conventional commit types ([`4eb904e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4eb904e274e3db9ee1d6e83c279d567207587599))
- RELEASE_PAT fallback for org-blocked PR creation ([`2533aa7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2533aa7f5e526db4bfd2689ae5c9a4e00cfe4cd9))
- reopen release PR if the previous one was closed without merging ([`5aad596`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5aad596128499007ad82ee57422f7cfa9779417b))
- PR-based releases — bot opens release PR, tag on merge ([`32dd56c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32dd56c244e801b09b849f66289886dc0fe2e02c))
- auto-release on push to main via commitizen bump ([`9218834`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/92188345a089832e3decb8cff58deaf710c238e3))

### Test

- **plugin_management**: fix collision refusal ([`0b2bbd4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0b2bbd4b63560db0a575e8a5445229507371cff4))

### Chore

- **device_viewer**: lower message-buffer publish log to debug ([`cf8e7a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cf8e7a23a5bae1ff46017e6af354977fb6a58ae3))
- **dropbot_tools_menu**: clarify chip-inserted connection log message ([`366c8f3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/366c8f3fdc780a40c9d7259a6b4fdd71fe15ddbc))

## [v1.2.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.2.0) (2026-07-15)

### Feat

- **plugin_management**: read plugin docs URL from distribution metadata ([`800bfe1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/800bfe1cd3218639dbbecb6cd8dfe74a42d5ca44))
- **pluggable_protocol_tree**: add Unfold Group action and grouping shortcuts ([`238c7cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/238c7cbb8c657e44951a078d67608e86b6b6c3c3))
- **device_viewer**: inline text-editor channel labels ([`ef2afb7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ef2afb7460757283584eac70aa1d17c617c76d5e))
- **protocol-tree**: WASD step nav, Ctrl+arrow phase nav shortcuts ([`395c268`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/395c268d23eefa78cb3aa656f46480b6328ed1f9))
- **quick-actions**: keyboard shortcuts + auto-append to tooltips ([`cfe5869`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cfe58697046a94f8bb6af90d23835a5747d105ef))
- **protocol-tree**: keyboard shortcuts for the navigation-bar buttons ([`6df8621`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6df8621974899a8f092e3967ff9f3791326b6996))
- **protocol-tree**: keep horizontal scroll when switching steps ([`3895a0b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3895a0b2984b5804065d86f27f6a2487189cb43d))
- **protocol-tree**: Escape clears the step selection to free mode ([`81f9dbf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/81f9dbf86da36240d68badbfaf2c30de40760206))
- **protocol-tree**: Fold into Group context-menu action ([`fffaf51`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fffaf519a8224b95d6b7c87faa884d18d31df01d))
- **protocol-tree**: generic row_selected/set_cell cell sync ([`2e9244e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e9244eff6358324e187f35d7bd948851a5cbf80))
- **protocol-tree**: add stop-aware ctx.sleep with timer freeze ([`727e461`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/727e461ef347a6916eb8407b02158e6193f218c9))
- **device-viewer**: crop/export any recording + auto-fit on align flip ([`0b038ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0b038ef87242a463625a98739b125e8ce9726cf2))
- **device-viewer**: move camera preferences to a Video Settings tab ([`d24f7fa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d24f7fa3d625bbd8e90396384a87ba63cd7591b7))
- **video-protocol-controls**: use step dotted path as recording step id ([`32036c5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32036c54f10b102e0df604e0e7eaf437f742f063))
- **device-viewer**: video recording preferences ([`f5172e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f5172e12f60436264fe371e5f97c7d661579bf8a))
- **device-viewer**: interchangeable, preference-driven video recorders ([`eba3322`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eba3322f24d9a66a21915a712172dc1d7551173f))
- **device-viewer**: pin constant-quality encoding on the recorder ([`9287997`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/92879974e06f9ff2a73249f967b5028c6c990944))
- **device-viewer**: Recording Viewer dock pane ([`0fc66d9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0fc66d9a51330120d55a60b19269504795eb2c41))
- **device-viewer**: native hardware recording + alignment sidecar ([`89c233e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/89c233e6145fdc8d3c037eaba0f3c3b5c40273ea))
- **utils**: stepped slider editor for fixed-increment float ranges ([`97ff1b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97ff1b856afdb4ea99b466024de298c8c9742e7a))
- **device-viewer**: Live feed checkbox for provider camera sources ([`f9a4b30`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9a4b3050cd38717c61b256af4bd2ef3f5f7f582))
- **protocol-tree**: dialog-editing views via edit_dialog hook ([`7b40de5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b40de50cccb651aeb39e0c1aedfb185647aad36))
- **device-viewer**: raw-only ASI captures; no recording for provider feeds ([`aadb92c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aadb92c24dd08a0b342e286a13390b77d93bf751))
- **microdrop_utils**: icon-button and dynamic-combo traitsui editors ([`5749417`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/574941703473811655a94f21092c945b5c79a3ad))
- **device-viewer**: camera-source extension point ([`805236b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/805236bac3df4e228a1948d40b2ab097cd0cb8ff))
- **device-viewer**: throttle tooltip-redraw debug line ([`b971183`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b971183a1ef42e07413ca38c4fb00a43391dcd37))
- **logger**: drop third-party DEBUG by record pathname ([`86a443a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/86a443a1e580b704d2cc0228abc344c06e685b94))
- **logger**: repo-only debug mode + throttled hot-path logs ([`2fb54f3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2fb54f3d6aa0ecd421531034313590cd509993d3))
- **microdrop-utils**: whoami port identity probe ([`638bacc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/638bacc6d594863c8686513820eb9d0ba1a560b0))
- **device-viewer**: label_geometry anchor helper ([`0ef99b2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0ef99b2c0b13214c86014d90e8d49155ad01ef1b))
- **device-viewer**: flatten curved SVG segments ([`c1c57fe`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1c57fe58c80838d4d2de695817cf4f1f3214f41))

### Fix

- **dock-panes**: don't force-show hot-mounted dock panes ([`f3cf02c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3cf02c034b8b96a2089b6afbbec8dda1d65a91f))
- **quick-actions**: skip tooltip shortcut suffix when there is no shortcut ([`33efb7c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/33efb7cd11d43f5d8570d7ce6467a1f8ec7ff2af))
- **protocol-tree**: forward run-bracket hooks to compound handlers ([`270c286`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/270c28666971c8b65f0d0239cf280dade190d3b0))
- **video-protocol**: capture step_id uses dotted path to match recording scheme ([`76969a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/76969a488b5c0c43e03e69a8e73a1ce55c6a8ef4))
- **plugin_management**: restore saved layout after hot-loaded panes mount ([`c4136b9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c4136b99c0fe4e7adac0d5ef8d33416118f235f1))
- **device-viewer**: keep alpha settings adjustable while protocol runs ([`06438c9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/06438c98d9a7d92ea36da2e5730d8677ec1a7196))
- **application**: tolerate no-Redis at menus import ([`cec67c8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cec67c88b6d6e7fa6ac65a972490920d40707782))
- **device-viewer**: ignore protocol-side route colors ([`8d82366`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8d823668b1e6b29e08477d24ed32c2df256ef9f5))
- **device-viewer**: apply display state as a diff, not reset-rebuild ([`99d498c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99d498cca88619b08e3fc914615ba098150d097f))
- **protocol-tree**: route execution mirrors the device viewer ([`197f062`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/197f06288aaf90806e068d94a80a85ff4a406a13))
- **utils**: stepped slider readout follows user drags ([`b8ddcaf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b8ddcaf9b9175374c331af02d9206ad28524b056))
- **peripherals**: announce monitor shutdown without reading _searching ([`da8df41`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/da8df41cc8db4bb23ad2caf0c57b44b564c51e46))
- **plugin-management**: persist group toggles in app preferences ([`892d11d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/892d11d6ed1b2421de5b4db35a0a6d086cf4aed2))
- **logger**: write log files as utf-8 ([`51823de`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51823de5f4da93c3bba73a90d40fea3e03518119))
- ascii arrows in log messages ([`964fb0d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/964fb0d88cd080199a65dee3e1f61a5701f32658))
- **microdrop-utils**: never fall back to a busy port ([`4789174`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/478917421a6eda45201c6f6839c5e98ebf53abac))
- **device-viewer**: re-pivot label rotation on refit ([`a2d3927`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a2d3927bea82d096dad91d70ce459773981b25bb))
- **device-viewer**: draw channel labels above all shapes ([`f5f54f6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f5f54f6f9f140e60180e04d1fbcda870a7583451))
- **device-viewer**: anchor channel labels inside the shape ([`1d675f1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1d675f1e4e0250c70b7599e140115386777130e1))
- **device-viewer**: repair electrode rings at the source ([`c025948`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c0259488639c759540aed7999019f3cec99dc563))
- **device-viewer**: keep largest lobe of repaired rings ([`d36442b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d36442b7b8107f6ba1784730d2e0f63677b7cd26))
- **device-viewer**: repair self-intersecting rings ([`fcd0942`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fcd0942699b1d6c48905c65f37d1fcf2a7d9935f))

### Refactor

- **protocol_quick_action_tools**: move New Group shortcut to Ctrl+Shift+Return ([`95875bb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/95875bb5d5c19190fce56dc4eb5a5ebf72a3be33))
- **quick-actions**: carry the dock pane in the action context ([`f06fdbb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f06fdbbddc764991fdf24f52cab2bb7ece060275))
- **device-viewer**: render-perf review cleanups ([`945d2d4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/945d2d410353ef33ddae6697934dd9ddc5f64105))
- **device-viewer**: typed traits in RouteExecutionService ([`b7a6763`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b7a676359c7b5bec4a15409725398be3ca36c90a))
- **utils**: fold the plan builder into the params entry point ([`5537714`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55377148eaa7b281b1a3a616e2fdd08e2e65b874))
- **utils**: centralize route-execution planning ([`a67eddd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a67eddd8b5b50a5386cee1286a11080c5ea60ed2))
- **device-viewer**: feed-owned streaming replaces Live feed checkbox ([`e56ddab`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e56ddabfff52e67b7d59dc1d0a99f81db1369d88))
- **device-viewer**: repair rings in one place ([`fb03582`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fb03582440ecf401219c937233c2b9e87b386218))

### Perf

- **device-viewer**: move capture PNG saves off the GUI thread ([`788e778`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/788e778a431ac0f1e8df3f780495077f2e31346c))
- **device-viewer**: cap preview frame rate without touching recordings ([`72dfa98`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/72dfa98fd3d1384eda10494838a0a4a963df1558))
- **device-viewer**: skip whole-model serialization during route playback ([`30ddd43`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/30ddd43975bab91dfdfe33ef2b30bb79601ec03a))
- **device-viewer**: gamepad poll idles without a controller ([`9fa57a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9fa57a2b8e935af1c41f94d5e941f285d62afaf3))
- **device-viewer**: recolor proportional to what changed ([`64900e9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/64900e98360c3cbc48577bfcbed8f17fd0e394fe))
- **device-viewer**: repaint only changed items, cache static geometry ([`15890b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/15890b8d105451f00532f778943dbda2bf20ba59))
- **device-viewer**: stop rendering provider camera frames in video layer ([`31a4341`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/31a4341bbd67358f9cc6ed6d726d164960554ed5))

### Docs

- add developer workflow section to README ([`53983f1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/53983f19a8a755adf79713e6ee667ee15671cfd0))
- point hook setup at the pixi setup-hooks task ([`12bf6ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/12bf6ef17626175f53d277fe983c2d7bd8a19492))

### CI

- local pre-commit guardrails (conventional commits, scratch-file block, ast check) ([`7baedb9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7baedb95db4205eb9f840700f5cf93a9d64e93eb))
- annotate release tags so --follow-tags pushes them ([`2618022`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/261802203b59dfcca6133dda29a14eb491f39113))

### Test

- **device-viewer**: cover mixed arc + straight path ([`58c33d5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/58c33d57db19c2a96103dde7c710f3a5994036f4))

### Chore

- **microdrop_utils**: quieter port-scan logging ([`39f0227`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/39f0227dc2ea703b5e4ea35be82c9b6b28c03e2e))

## [v1.1.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.1.0) (2026-07-06)

### Feat

- **application**: extra_plugins_loaded event fired after group-plugin restore ([`74923cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74923cb07a4570c84170d90c8c46cc251e3375a5))
- **utils**: ToggleEditor accepts non-string on/off values ([`89b09c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/89b09c10703fa68746cd0ab1ae221edd20af914c))

### Fix

- **logging**: demote the per-message listener log to debug ([`d9a66af`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d9a66af0c5f007935c6790bbcfac1b4a5b0f7606))

### Refactor

- **utils**: move the in-place toggle into traitsui_qt_helpers; name both toggles ([`ceb0d2f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ceb0d2facafcfda59cfb05ebf44a91343b986442))
- **plugin-management**: drop redundant version from plugin manifests ([`59dd5cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/59dd5cb0846d6f849a3723bc2f6f688d84c1b10c))

### Docs

- **examples**: complete the scipy_analysis demo plugin package ([`c675c80`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c675c80d5de94a13d237b0f68d49da6ae7c9a300))

### CI

- commitizen versioning + conventional-commit PR check ([`8a81fbc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8a81fbc27510e3baae22653b7a9d50a2b5c5b550))

## [v1.0.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.0.0) (2026-07-06)

### Feat

- launch-time plugin update check (background fetch + dialog) ([`4f8cb73`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f8cb731e865ddc7baa671d156d8104a37c75219))
- update-check dialog view + controller (Update All -> relaunch) ([`b7654b2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b7654b29b7d5ad8f9232629a183294270a4b6802))
- update-check diff model (compute_update_report + UpdateDialogModel) ([`56a2143`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56a214398565ee2941c0acf1532def8e199bc570))
- installed_plugin_dists() — installed MicroDrop plugin dist versions ([`4d44fc8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4d44fc8e78bb03f6cacacd0b7edfb3bb8c14eeb8))
- priority ordering for contributed status-bar icons ([`b0de3cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b0de3cb6deba80a2601bb2649a03c5da7ee0ec3e))
- register StatusBarPlugin in frontend plugin list ([`7b218ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b218ef7ab3aa4f8bf89f2cc98395be78e447948))
- BaseStatusPlugin contributes to status_bar_icons extension point ([`c71cacd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c71cacd38cb584147b4b999799391ebbe1995881))
- microdrop_status_bar plugin with status_bar_icons extension point ([`6b55947`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6b559474fa771a2b42ebd460164988277e47789b))
- **plugin-management**: split device groups into UI/backend + group-managed protocol controls ([`d6316e0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d6316e02cac6733905879fedb9bf4b30a7960dc1))
- **plugin-management**: full Manage Plugins window (apply/install/uninstall) ([`57f1394`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/57f1394f23c0c6bc038f041d3b3b43600c2e31bb))
- **plugin-management**: Browse Plugins dialog (install from channel) ([`51e74b4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51e74b4b03cde0e26d42c9555e86e5711ce7377d))
- **plugin-management**: threaded progress helper + relaunch into pixi env ([`f2b6dee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f2b6deec70b67c747617ef5deacc4a477a582682))
- **plugin-management**: conda-channel package installer + app-data cache ([`addc6eb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/addc6eb0b626827d0581c08a0a9e66c3105f1c47))
- **plugin-management**: manifest-aware group registry ([`9a6ddce`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a6ddce7a417d53e0e24dbd622d92fb57506f153))
- **plugin-management**: TOML manifest parser + entry-point discovery ([`85baf8a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/85baf8a87fada5c55772db1a2c413820cb22bd35))
- **plugin-management**: Manage Plugins menu action + service + launch restore ([`9bb3221`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9bb322180191d8861fd97ab464b38654bc112664))
- **plugin-management**: Manage Plugins dialog (toggle groups) ([`d754b02`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d754b021423ae950350f149af26a7327c4c8f7a7))
- **plugin-management**: PluginGroupManager with built-in Z-Stage/heater groups ([`4a93032`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4a93032acba74232c8815c3c1052bed7b654e9e9))
- **plugin-management**: reactive TASK_EXTENSIONS mounting ([`564d92f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/564d92f9d694afccf7ba9b7c480ee5465e516d56))
- **status-panes**: on_live_mounted hook for runtime hot-mounts ([`122c059`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/122c059235a53d4a322b6a5c0aecd827e577b51a))
- **utils**: runtime add/remove of dock panes + live menu-bar rebuild ([`99fc3b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99fc3b0e0aea035993b7f0c9565101c39727bfae))
- **peripherals_ui**: PeripheralMessageHandler on the shared base ([`cfd2318`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cfd231884f98687fdbd2ca3f61ca22ac016fd569))
- **heater-plots**: teardown the plot listener on pane destroy ([`5003775`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5003775480cca99315dfe57202907bc1485cb991))
- **status-panes**: destroy() teardown on BaseStatusDockPane ([`521d7a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/521d7a494bb158770f9dfb55e79f5ec9a35adb8d))
- **status-panes**: teardown() on BaseMessageHandler + interface ([`b33f909`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b33f909d3e06d67e6606e52b18bf2357dcc19bed))
- **utils**: unregister helper for dramatiq listener actors ([`6d16825`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d168257de4a657e8e9210debf29417a4c09a513))
- **heater-plots**: Pause and Stop buttons on the plot pane ([`6071336`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6071336efb9030623ad1da9913f8abf4c95ab5f0))
- **heater**: add live temperature/PWM plotting dock pane ([`4df4326`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4df4326af67cd790f28b9e85bde5c46f5196bda3))
- **heater-config**: show a scan summary label after a sensor scan ([`ce24be9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ce24be92b31027f1fb1ec91d23bdda7b66e235b8))
- **status-panes**: add RealtimeModeIconMixin ([`e8cb9a1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8cb9a1a49e4bb7a79f9907a514954b597f0cc81))
- **ppt-status**: freeze timers around StepContext.wait_for ([`7550dda`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7550dda019a8fa016781d30cf2a13c88d18fddb8))
- **ppt-status**: wire ack-wait signals to the status model ([`7a87748`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7a877488aa4d9f3a8e4f5e320bdf8a5eb464593c))
- **ppt-status**: add ack_wait_started/finished executor signals ([`f3f6dc9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3f6dc960a6acb0f2bb405d46d7dfa8d88bbde5c))
- **ppt-status**: freeze status timers during acknowledgement waits ([`ca02848`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ca0284889a16bb22b831150449575a42351136cb))
- **ppt-status**: add ScopeStopwatch.is_stopped_at_zero() helper ([`7032054`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7032054d463f5f3fa0b4caae8b75fa53260d5ef0))
- **heater**: heater temperature protocol column (Phase B) ([`559652a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/559652a47afeb8ffea8580958c3f0bb93279d688))
- **heater**: protocol set-temperature with reached-within-tolerance ack (Phase A) ([`94f5157`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/94f5157ab9d28c11a8de867235eb60a20d9e4938))
- **heater_ui**: Save & push to board button (Phase 3) ([`63977ee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/63977ee355e7ec0a53bb87246b7c0dd096c3b101))
- **heater**: save-config-to-board push via mpremote (Phase 3) ([`116ccb1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/116ccb174b740923898d7eea30098ede981fb8d3))
- **heater_ui**: available-sensors reference + HTML de-emphasized labels ([`9e89c1d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9e89c1d38ae8962097f721c9ce89dd2f773ef244))
- **utils**: add HtmlLabelEditor (rich-text QLabel bound to a Str trait) ([`d837e82`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d837e82f3ac601cfbcacd90c12e23358b9f674b4))
- **heater_ui**: edit + save the sensor/heater config (Phase 2) ([`0113953`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0113953368ff449a5bfb8fb181318d1f272f93f7))
- **heater**: pydantic validation for sensor/heater config edits ([`4363663`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4363663342f07937e779537f92896047f4856abd))
- **heater_ui**: wire the configure-sensors dialog into the app ([`20200a3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/20200a379dca8d75a131d87418bf30a723911b25))
- **heater_ui**: configure-sensors dialog (Phase 1, read-only) ([`d0fdd38`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d0fdd3825be1d95c574860460df85903379eb782))
- **heater**: backend config ops for the sensor/heater configurator ([`b8c941f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b8c941ffc59fa090e2dbf422556b548d3042262a))
- **peripheral**: publish search-stopped when the monitor thread terminates ([`26455c7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/26455c714b591c082a5cfc0e0b754027e303281b))
- **status-icons**: flip the status-icon tooltip while searching ([`50d78a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/50d78a2114c0a549ab047a5b02956e66dcaf8e95))
- **status**: add a searching trait to BaseStatusModel ([`059c6e3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/059c6e340555ae0187abc74bdccca47afd881e7d))
- **peripherals_ui**: re-enable the Z-Stage status icon if a scan stalls for 10s ([`8741d6b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8741d6be5010504952a8d49a3c7888c9fbed9278))
- **heater_ui**: re-enable the status icon if a scan stalls for 10s ([`d64d121`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d64d12182ea186f7e093f004364d869196be3653))
- **peripherals_ui**: make the Z-Stage status icon search for a connection ([`3deab29`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3deab290b9f3021c36ad5995d96767250f4fe7d6))
- **heater_ui**: gate the status-icon connection search on an active scan ([`d65ac04`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d65ac04bdf2decc6cec72fcf3896eb16598e44bb))
- **peripheral**: publish a connection-search signal from the monitor ([`ef68954`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ef689545a4064201320e941325030092f58dd232))
- **heater_ui**: make the status-bar heater icon search for a connection on click ([`90729d0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/90729d01537c98ce805eb1591e01a431abb0de68))
- **utils**: add ClickableLabel (QLabel with a clicked signal) ([`99cd794`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99cd794037fc515d6a9fbc33f9facfc224588779))
- **heater_ui**: stretch collapsible sections to full pane width ([`38c2071`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/38c207123527a41c74a4effeb488f0046faee168))
- **utils**: add stretch_group_layouts_horizontally helper ([`bc61184`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc61184797ed093b325679eb6f95d8afd1c52982))
- **heater_ui**: make the heater pane resizable and scrollable ([`8299eed`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8299eed8b1a289d306d8ef2350c5598be0f4d034))
- **heater_ui**: render section collapse toggles as arrow glyphs ([`0024a7f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0024a7faf2129ea19c8918696cb1ebb1055ba902))
- **utils**: add IconToggleEditor (Material-glyph Bool toggle) ([`f54fef1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f54fef123c689623743ddf036a7814337d383973))
- **heater_ui**: make every control section collapsible ([`e8ddf3e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8ddf3e38b6067a7bd73c794adc8ea64615f897c))
- **heater_ui**: add per-section collapse toggles ([`878a98d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/878a98d53e924b5bb9d6a8d81c02dfc8eb929cf1))
- **heater_ui**: restyle the mode switch and reorder the control group ([`6929a33`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6929a336be6e81ee9cf21c3b98de619221e08eab))
- **heater_ui**: track live PID duty in the PWM setpoint during Temp mode ([`8a16335`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8a16335a5245a6ebd3057ec3cf060e69674ea2ce))
- **heater_ui**: default the mode switch to Temp (closed-loop PID) ([`c15f523`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c15f523db03ed7f7052d04b5ee74fa991e240145))
- **utils**: expose full Toggle colour args on the toggle editors ([`4953d64`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4953d6462aff2205a6967e98924d9affb74d8f54))
- **heater_ui**: render the PWM/Temp mode switch as an AnimatedToggle ([`718fbf0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/718fbf0114a438232cdf1bb3f986647d45b8a1a7))
- **utils**: add AnimatedToggle slider widget + AnimatedEnumToggleEditor ([`ae92ee7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ae92ee73d2db5dbc393f8303b28e5b56cfc12208))
- **heater_ui**: toggle PWM/Temp mode with a button instead of a radio ([`0e6a229`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0e6a229055ef61588ce8576576e83a3d73b71eac))
- **utils**: add EnumToggleEditor for two-state Enum/Str traits ([`437f301`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/437f301c7ca2bf687ec910a64573908cc394027d))
- **heater_ui**: render a status row per heater via ListEditor ([`ec01413`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ec0141320d485e6bc5eab03670d40930b9df0984))
- **heater_ui**: per-heater status readouts driven by PID_<HEATER> frames ([`281390d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/281390d541708c83fe93e5b3eadda4fdc9c6da61))
- **heater_ui**: PWM/Temp mode radio in view, per-mode setpoint enable ([`455a4e9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/455a4e9b6e49e727dac6e40ee25e85f9fff71259))
- **heater_ui**: gate heater commands behind streaming, apply mode on start ([`39d294b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/39d294be4917c53e107329900c5abb3c40f9200e))
- **heater_ui**: replace PID toggle with PWM/Temp mode radio in model ([`d78824e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d78824e821145a90f96521874a14a517414f1475))
- **heater**: gate temperature setpoint behind PID + 'applies when PID starts' warning ([`6f3bd59`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6f3bd5971e61cc5bca8c18e520c656a93f687f78))
- **heater_controls_ui**: enabling PID auto-starts streaming ([`9f3ede4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9f3ede4b26146f5378f3c24c65a490a870f273dd))
- **heater_controls_ui**: push current setpoint when PID is enabled ([`4dfb342`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4dfb342e752c9d7444c80cbacd5c594de6b865ec))
- **manual_controls**: configurable labels on ToggleEditor + add heater icon ([`1a64591`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1a645918e6fbc5ef9139fb17528c6638d9cf6853))
- **heater_controls_ui**: dock pane for heater monitoring + control ([`43594e7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/43594e7035e1b8957a4e3e910cca1a3ff43375a7))
- **heater_controller**: publish telemetry + whoami on connect ([`4fbc65a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4fbc65ae10c9a672340eae1e518a7f15de024ad2))
- **heater_controller**: typed command topics + heater discovery ([`f166fd9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f166fd9c9465ee367172912b6bb269f167119f06))
- **examples**: register HeaterControllerPlugin + add heater backend demo ([`f137311`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f1373111590c55b4ff9fff9819dd86a1a23de35e))
- **heater_controller**: backend plugin for the heater via the base classes ([`55683ed`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55683edb2af274490ef40b3e7705140dd9f7e034))
- **backend**: add generic peripheral_device_controller_base package ([`f01f94a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f01f94ad80dc76a69202d7bf8522685fa0d575f0))
- **device_viewer**: seed device repo with bundled SVG files on first run ([`dff9c71`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dff9c712e1add82ab7f85219ba6a7cd27cc2e264))
- **#477**: route-rep time-expired dialog + dynamic-loop decision logging ([`9338412`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9338412fcf821ab58b8ca83956e5a9b8033aebd5))
- **#477**: warn before leaving idle phase on phase-bar seek ([`62bedf0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/62bedf0204aa3295d6df94dfaf9c10fb06cd8dc6))
- **#477**: phase bar shows unique phases + dark-yellow idle cell ([`27204ea`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/27204ea06ecb74e48fe185b985aa4dbed17f0342))
- **#477**: guaranteed-loop gate, idle phase, seek re-entry, mid-loop-expiry ([`5bfc3d7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5bfc3d73d6292958b154c10dbae87259e6da18e2))
- **#477**: executor signals + controller wiring for dynamic phase/idle ([`9ad0661`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9ad066193aae04b4a23db35defb1a85a3353c632))
- **#477**: status model unique-phase + idle state for dynamic loops ([`8a4e146`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8a4e1469c655eb91dade21ab76030ae772625898))
- **#477**: pure duration-loop gate + idle-cell helpers ([`c15e2dc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c15e2dc6c5034eba2e5073cbea33b98c98f39034))
- **#477**: warn before leaving idle phase on phase-bar seek ([`99c7b58`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99c7b5823558354861f86755984603050d81416e))
- **#477**: phase bar shows unique phases + dark-yellow idle cell ([`8a165ba`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8a165ba2cdce0f96444852ffbcc5061f32071209))
- **#477**: guaranteed-loop gate, idle phase, seek re-entry, mid-loop-expiry ([`f152daf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f152daf02fb3d071984aaa78c12847b407250c3a))
- **#477**: executor signals + controller wiring for dynamic phase/idle ([`058bae1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/058bae1edb034158a039d0e0d5dc72d19f74b17a))
- **#477**: status model unique-phase + idle state for dynamic loops ([`bb0bed6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bb0bed6937e69888ae84abe27b4ec64a4c30cba7))
- **#477**: pure duration-loop gate + idle-cell helpers ([`e7bf197`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e7bf197ab788c198442a8fde5f42e1ef4fe0d1e3))
- persist protocol-tree column order across restarts ([`2513c91`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2513c913d759a4faeb0410f2998624b7cbfc5f6a))
- **advanced-mode**: device viewer editable + actuation write-back in a run (#434) ([`a334d02`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a334d026eb6ff83ead321cf4015b57138cd544f6))
- **advanced-mode**: keep protocol tree editable + live-apply edits in a run (#434) ([`69c45c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/69c45c19636fbfcb2322c89d083fef7ae478019f))
- **advanced-mode**: thread advanced_mode through the protocol context (#434) ([`6f76e0b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6f76e0b58e1bd28bccdba83cd6912442ca6ab229))
- **volume-threshold**: add Rewind recovery action ([`8de331f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8de331f6c6e4b7e18a0a7a18ef69b31373850283))
- **protocol-tree**: separate Step Rep and Phase Rep selectors side by side ([`358b323`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/358b323615e55cdf13036f61cccc15b8957ae9b5))
- **protocol-tree**: jump to a specific step repetition from the timeline ([`87d2176`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/87d2176e5b3e4b997841cd96ca67797e98c3b532))
- **protocol-tree**: step-rep collapse + show-full timeline expansion ([`9dadca4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9dadca4b255cd957480b7c61bf73a7911eb5d600))
- **protocol-tree**: collapse phase reps to base loop + Rep selector ([`e5d754c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e5d754c9da2f991c55a76d001b7c77a9eb7bddac))
- **protocol-tree**: throttle timeline drag seeks ([`68e2942`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/68e2942c385158f90cc152c78d9fe132b2fc483e))
- **protocol-tree**: group tint bands + relative drag in timeline ([`f2a84a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f2a84a7f4511b6174108d0fe44890c65cf17e280))
- **protocol-tree**: show phase track only while protocol is running ([`fd0b216`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fd0b2163f60d8f7d78c5e47c7538f9b054489ab1))
- **protocol-tree**: timeline current item as a highlighted cell box ([`74d2d47`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74d2d47fcf3d10fb1e402bfff8f9e51300ba56f7))
- **protocol-tree**: wire TimelineBar seeks through the controller ([`05bc0c6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/05bc0c60bc16b3b3c31fca9fa75d0ee4a89986b0))
- **protocol-tree**: mount TimelineBar under the nav bar ([`1fe0e26`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1fe0e266de0576c4d71c4ae064cb6e0f8e21b253))
- **protocol-tree**: add TimelineBar seek widget (view) ([`37b5b64`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/37b5b64110a7891dc789785e419981094f7c56ed))
- **device-viewer**: load persisted calibration data at startup ([`ba1d53c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ba1d53c30bf2ae0adb6145a3a237a06c5c8b134e))
- **device-viewer**: persist calibration capacitances to preferences ([`88cd957`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/88cd957e6007b3f1113d3701af7849f3a0708769))
- **protocol-tree**: persist and restore column visibility in the tree widget ([`097f84e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/097f84ea317efd5a845a84427c994069bf2ce556))
- **protocol-tree**: add column-visibility persistence store ([`8140067`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8140067a46d986e0855c0f982f9c8bb13bdedb08))
- **run-script**: add --plugins arg to select frontend/backend/services layers ([`a3cfe7c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3cfe7cb77305d6bcc705d76a3a47eefb7938521))
- **message-prompt**: offer Continue / Stay Paused choice at the gate ([`b61573f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b61573ff4a028107be755546b28f329b712b815e))
- **dialogs**: tag secondary buttons with explicit role ([`f1cdca1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f1cdca19e3101c08d7207c9effd2ae459da1a91b))
- **plugin**: register message-prompt column in the builtin set ([`b46cf7d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b46cf7d4f9781b4892a58ca6b3a7c84ebd0100c1))
- **columns**: add per-step message-prompt column ([`ba5135c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ba5135cd0e6d027e181dc21d84e5fd718a002ea5))
- **executor**: add pause/resume + worker-thread wait() primitive ([`d558e0d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d558e0de15af0dcba4561018b5a8b5f53ae585b7))
- **device-viewer**: route rotation through model + apply at startup ([`6b957cd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6b957cd7d09fe0b5d04fd3a4beebf58ae00c94d2))
- **device-viewer**: load persisted device-view rotation on startup ([`693ff93`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/693ff93b32329e0d69b1ad06ab23f72a2fd9e456))
- **device-viewer**: persist device-view rotation on model ([`b980424`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b98042464a3410c082b28f38431433af312f0fca))
- wire up reboot action with confirmation warning ([`3fcc9b9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3fcc9b9a5fdca634cd03e5ed0e8c745e241bcc7d))
- add dropbot reboot request handler ([`6a6c749`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6a6c7490cdc8f670c346e82f39fba639dbccacf8))
- gamepad remapping, hot-plug, live capture, and reconnect ([`31a483e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/31a483ecc39bddde0421ce673c29def9d0753553))
- add gamepad connection indicator to status bar ([`2bb6f1f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2bb6f1f67c4b588ec95f021848757f7873481fcc))
- add joystick icon glyph for gamepad indicator ([`f755c4e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f755c4eb738069eba06fb0311487434cda90104f))
- add simulation buttons for shorts, halt, and chip toggle ([`57430f3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/57430f36c6be79806c09f7f01827fe25eeaadecc))
- add mock dropbot plugin lists to plugin_consts.py ([`00eb726`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/00eb726cd403482ffc68c039f946f49a722de39d))
- add warning dialog when leaving free mode with unsaved changes (#278) ([`9f51ee9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9f51ee92330daa4f5862c66933a9bba0e481cd71))
- add popup warning when starting protocol with active video recording (#279) ([`dafcb51`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dafcb51835970be221845734468fdd4d8db5af4a))

### Fix

- silent skip on any update-check failure; drop unused logger ([`e4f577d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e4f577d558641f9b6189ecf237060052df66e357))
- build status bar at application_initialized, not active_window ([`55cb801`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55cb801ac116314f3d5a7fc5e070bf3547f8a4a1))
- guard status-bar icon container access against destroyed window at shutdown ([`8ba65b9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8ba65b9ee45f0a2a8560f2894afcfc03140a916f))
- **plugin-management**: device group plugins have ONE loader — the group manager ([`5cdf5e4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5cdf5e498f2a0f8e6e833c3e85f1da57489222db))
- **plugin-management**: startup crash from early restore + broken adoption ([`97e6b67`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97e6b672c5f721d3768e19bad3ebcbb1630feecd))
- **app**: keep splash screen on top while the app boots ([`b4428d9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4428d9037b8948d262e501b63b11fea5a2c602c))
- **heater**: re-apply @observe on the _populate_status_bar override ([`a02389f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a02389fed333aae58646f245e86157c202b1f84a))
- **heater**: resolve protocol target to the real board heater channel ([`f968949`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9689497322a18ca78fcfd7391d47f075dfc5ecb))
- **heater_ui**: drop the readouts scroll area so the height cap is tight ([`61edbfb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/61edbfbcf1466afb0465fb0e8e246e5359022885))
- **heater_ui**: stop the heater-status list from leaving a big vertical gap ([`c60b8b9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c60b8b90074f68ab1b0c3b6fbc822e3d61c654cc))
- **heater_ui**: refresh from board clears the scan (status back to In config) ([`2a97b47`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2a97b4712552d35c31c96b3c8bf17f43355707a8))
- **heater_ui**: refresh updates the config tables in place + size columns to content ([`93eb862`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/93eb8626eeb9da46d30fe022092d3c8d9a661657))
- **heater_ui**: show the full wrapped help text in the configurator ([`06e4549`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/06e4549d5b55d61bca669269aaa77a07ae852d10))
- **heater_ui**: wrap the configurator help text so it doesn't widen the pane ([`127a0a0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/127a0a085d22a19f905447a38aaf3a4fa789c696))
- **heater_ui**: disable the status icon immediately on a search click ([`3400c56`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3400c56685c0e12e467b8c96fc1e8233b44c02e1))
- **peripheral**: re-announce search state on every start request ([`defc723`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/defc723e33101c272080606e919fa6859fd6ee80))
- **utils**: only stretch section boxes, keep their contents left-aligned ([`886307c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/886307c59a8f773c48912d8beb7ba02fd9afb526))
- **utils**: use Qt.AlignmentFlag.* in stretch helper ([`0e0fa05`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0e0fa053c5da1f05b2454211eaba064a168a3984))
- **heater_ui**: log telemetry parse failures instead of swallowing them ([`da704f1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/da704f1d5284f2b30c7c2d0274f3499bef251baa))
- **utils**: wrap Toggle bar/handle colours in QColor ([`a6e449a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a6e449a348903b967653c44dc95c6cd878d37d52))
- **heater_ui**: correct main temp/PWM readouts from real board frames ([`400ee3f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/400ee3fd7cd60dda440a320e025afc8f98cb830d))
- **heater_ui**: select main PWM readout by frame, mirroring old UI ([`e327245`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e327245786019ee3edb569fcf9c62318417f8ff4))
- **manual_controls**: ToggleEditor label now updates on click, not just trait ([`60a279e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/60a279ef6af0832c31b3f102d15df6758b9e797e))
- restore files unintentionally bundled-out of earlier commits ([`49d7879`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/49d78797162425d83bba08e81a4b3e1d981a3d47))
- drop dead EXPERIMENTAl_PLUGINS import in frontend run script ([`0f2832f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0f2832fe7f758b9dfd661205d7e663cfcb85c542))
- **#477**: show time-expired dialog while paused; complete-loop stops at start ([`f875dc6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f875dc68af0eafff8372095571d32673d4c42ae4))
- **#477**: wake held phase when rep-duration budget is crossed so overrun dialog fires ([`9a4bd9c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a4bd9c68140ee7c12f79ab7be146f07069a8f0e))
- **#477**: keep dyn_loop_active set during dynamic loop so timeline shows one loop ([`dc43767`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dc4376748794affefb901c07e4381eda9d413e4d))
- **#477**: in-loop seek checkpoint so mid-loop phase toggles reposition in place ([`8fd1b25`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8fd1b251d70f2869b331214c2e5088a7c79f8921))
- **#477**: dyn_loop_active flag fixes seek phase_total, idle preview, stale dyn_idle, static idle-tint (final review) ([`86f0555`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/86f0555cd81d72d60ec1f314db7989a98e12e850))
- **#477**: cap per-phase hold at duration_s for the worst-case loop bound ([`1de87d4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1de87d4dae3ab2d52ae2b702cbae5044a916d867))
- **#477**: resolve dynamic-loop resume phase from resume_target (review) ([`0c1f30b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0c1f30b8bf054148cd8a9a604e63079a5bce2e84))
- **#477**: keep dyn_loop_active set during dynamic loop so timeline shows one loop ([`a04678e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a04678e70e655d546420df7da0b2bbabe7514934))
- **#477**: in-loop seek checkpoint so mid-loop phase toggles reposition in place ([`1ecb51d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1ecb51d658cc097e68edf718bd0110256d42c43c))
- **#477**: dyn_loop_active flag fixes seek phase_total, idle preview, stale dyn_idle, static idle-tint (final review) ([`eda8e29`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eda8e2966fcdca50b340723cb833f5c3281491e7))
- **#477**: cap per-phase hold at duration_s for the worst-case loop bound ([`b3b39a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b3b39a4c00ad6a5d9b92b9a5c13065f494651bc8))
- **#477**: resolve dynamic-loop resume phase from resume_target (review) ([`d9dad75`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d9dad7533c4dc9982d6a1e281b3712255c091bea))
- **advanced-mode**: keep viewer editable when navigating steps mid-run (#434) ([`09a05c9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/09a05c9040a11663df721345341f78111f912852))
- **advanced-mode**: on_live_edit receives the ProtocolContext, not a StepContext (#434) ([`8d18138`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8d18138dbeb5cf1b379f0f00d306593da36843e4))
- **advanced-mode**: lock device viewer during a run unless advanced (#434) ([`e798e3a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e798e3a970fb0143dc61b1b90e26aa12bf3e402d))
- **volume-threshold**: rewind to furthest leading edge on multi-channel hit ([`2e6bfb0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e6bfb07786dcf39392deed62a55d4f2bac9aeb6))
- **protocol-tree**: update status bar immediately on timeline rep change ([`a16beca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a16beca591097ebb16099985f4d69af05849abdd))
- **protocol-tree**: step-rep combo live-updates and full-view frames drag ([`ee3344b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ee3344b682227af02ca670252fc3dd72a10ac773))
- **protocol-tree**: live-update Step Rep combo as repetitions advance ([`10798ee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/10798eeb5ee444d2c9b56325e14b3693d62b5990))
- **protocol-tree**: collapse phases off real base loop; show rep controls idle ([`6edd369`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6edd369dfa525c0ce26c1ef918eca67de9ec0a38))
- **protocol-tree**: count distinct steps, compact rep label in status bar ([`99c2468`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99c24689f1b99403f32685d059ceeea57afb6541))
- **protocol-tree**: timeline follows direct tree selection changes ([`7dfcd77`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7dfcd778efd16d0d7df43e9edcd713d2dbc11abf))
- **protocol-tree**: highlight current step tick; show phase ticks on selected step ([`d4038b5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d4038b563de439f7c7a80bbb8bdbc1ddb7db4cdd))
- **protocol-tree**: theme-aware TimelineBar running accent; drop dead color key; test _phase_index_at_x ([`40d485c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/40d485c0ad1246f97d6defb92e54b557711e420c))
- **dialogs**: drive confirm button colors by role, drop dead overrides ([`c9b054e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9b054e87bcc2b4ffe66c06d22efcc1e052363b3))
- **message-prompt**: harden pause/resume/wait against hangs and headless runs ([`b997882`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b9978827ff529213f1075489f6e4b458f9c1ba39))
- replace QTimer with threading for capacitance stream ([`e2d77e6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e2d77e64085aba0252ae21aec54be3f31ee6f910))
- address code review issues in mock dropbot plugins ([`3957c9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3957c9be55c3c59eb1c43e8130f7ef92120f4cac))
- remove unused imports in mock_controller.py ([`28ed2cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/28ed2cb380f9d8655231faf9c43e89b423a6d1da))

### Refactor

- run the launch update check via a dramatiq actor ([`39d2ef0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/39d2ef0b9780c1f8217c69f0c0f1b5540faa5cf1))
- strip gamepad indicator from StatusBarManager ([`d851e1f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d851e1fd0854b571c871f2e75423f3496487c634))
- device_viewer contributes joystick + recording icons via extension point ([`ff4c8ad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff4c8ad14fc918a6159436a9a2da445c9a3aa40f))
- move status-bar creation out of MicrodropTask into microdrop_status_bar ([`15f3c08`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/15f3c08d571f2364011de0db366c938681924748))
- BaseStatusDockPane contributes status-bar icons via extension point ([`94b4950`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/94b495027477eac76c309e6b0a9121058ebbeb40))
- **BREAKING**: extract heater + magnet/Z-Stage stacks into standalone plugin packages ([`6027cf6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6027cf61630a430bd0d0d34050d31ba761378eb6))
- decouple src from the heater / Z-Stage device stacks ([`379d9b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/379d9b895d6c908fbf1f13d6b9ac1a68878e2df0))
- **peripherals_ui**: drop the superseded dramatiq controller pair ([`2b82ba3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2b82ba33f1984c0ce7473dd96d069ad0645f85af))
- **peripherals_ui**: move the plugin onto BaseStatusPlugin ([`c9c23ad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9c23ad83fdc98a168825b4a829a3b3051e2528c))
- **peripherals_ui**: move the Z-Stage pane onto BaseStatusDockPane ([`6d3a8dc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d3a8dcc5b5fd0f10e32a7041c1be8314bc8028e))
- **peripherals_ui**: own status colors + template contract on the model ([`3d34220`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3d34220190825ebc6c9a7e47f69893b85db1dc58))
- **heater-plots**: plot model to proper traits + pause/stop/hidden/revision state ([`edc955e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/edc955e1146b262d3a04d2b97736cd5a8f361542))
- **heater**: use the template's status-bar hooks instead of overriding wholesale ([`7ee1e58`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7ee1e5895ae679421ccdf8e90cf32c5e0c50323d))
- **status-panes**: move dropbot/mock/opendrop panes to the new template ([`21ab3a1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/21ab3a11b4ffd4625995f64e11385fa7b8e54e56))
- **status-panes**: make BaseStatusDockPane device-neutral ([`6985016`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6985016f83a6259155de9b2164c12996c59ae6df))
- **peripherals**: each peripheral plugin owns its startup search + menu ([`9676a1a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9676a1a97b97cdb997ffd775346c345319ed3a51))
- **peripheral**: publish searching state via a _searching observer ([`c097e55`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c097e5544a881d4e79f4e47a2468c8cd7ed97d33))
- **peripherals_ui**: simplify Z-Stage status-icon search to backend-ack only ([`4e90b0c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e90b0c871382797272e4c91fd0ff6418f97596c))
- **heater_ui**: simplify status-icon search to backend-ack only ([`da7fd5d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/da7fd5da73f45e52069469ddb3cb1e44a068a860))
- **heater_ui**: move the Search Connection menu into the heater plugin ([`cc55ebd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cc55ebdc29a9b26a9df1e6a18bf64328587f762e))
- **utils**: replace button EnumToggleEditor with Toggle/AnimatedToggle editors ([`423312e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/423312efe9a6eb56a08fe6857db4e08452222fca))
- **heater_ui**: rename stream-off setpoint warning + preference ([`92c9916`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/92c99162af3dc2fcf53e9feb57b2ce76fb9a5954))
- **menus**: move heater connection search into peripherals Tools menu ([`d49952d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d49952d3c6cd821af5f5415f6e72d3870e8b1dd5))
- **heater_controls_ui**: simplify pane to PID + Stream toggles ([`8320762`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/83207624af251aa9cba7f1ded0607182f455099b))
- **heater_controls_ui**: rebuild on the status-and-controls template ([`3fe3d69`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3fe3d69f8b3328479c6417bc751b8bf3ff8be5e6))
- **peripheral_controller**: re-parent magnet onto peripheral_device_controller_base ([`519a0e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/519a0e86d522966fd9e00a908c0799d4764b5a1a))
- replace device-viewer-sync Qt signal bridge with trait Events ([`704217b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/704217ba40f2719bd28787d5bf40dcc703d23050))
- **protocol-tree**: DRY step seek/preview helper; unconditional timeline running accent ([`0a355dc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0a355dc1cb7d1e13dd46d43ec66cdb9a5d9a052f))
- **dialogs**: classify dialog buttons by explicit role only ([`ebcd610`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ebcd61015d14271c7457211ae3446a81e2c1f6c6))
- decouple frontend/backend via pub/sub topics ([`a9f726e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a9f726e249632d70770582cbcf5aaf2af896fa4a))

### Perf

- **heater-plots**: persistent artists, gated redraws, clickable legend ([`7c941fa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7c941fa32dc8c23837221df28510c3eadf31ee16))

### Docs

- implementation plan for plugin update check ([`87ffd9a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/87ffd9a7a9a76a592fa4e950385a6dc361d83978))
- spec for plugin update check on launch ([`49d0542`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/49d0542c50cefe3fade03fd7f499e8c191500fe6))
- implementation plan for status-bar extension point + spec refinements ([`1047766`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1047766dfcee8c0e7e964bd5754772eeb1d97ff1))
- spec for status-bar icon extension point (microdrop_status_bar plugin) ([`4831da2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4831da2f0882cb9484b9225444d83c957cb66359))
- plugin development guide (conda-package + entry-point model) ([`b51029c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b51029cac12b753561a2328eac8c2295498ad07c))
- design spec for heater plot performance + toggles ([`eacb98b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eacb98bbc52e2ab8dd7f3213e334575cafe354f8))
- design spec for status-pane template refactor ([`1c5dbd7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1c5dbd715b9c64301d6c540e0a087f703dcf834a))
- **heater_ui**: fix stale 'mode radio' comment in view ([`88ba33e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/88ba33e3c9be98486a52ac86e7bb6c90f02a2a7d))
- **demos**: demo the Toggle and AnimatedToggle switch editors ([`884f822`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/884f82279cb4116b41de8f1933a6d410368c60b9))
- **demos**: show AnimatedEnumToggleEditor slider in the toggle demo ([`15c082f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/15c082ff72bc030484d0f2fdf580ccbdc2373bd6))
- **demos**: add standalone EnumToggleEditor visual demo ([`79366fb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/79366fbb3fb8d62cb12eb2edeb94ff189211cdb4))
- design spec for heater_controls_ui dock pane ([`1434ecd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1434ecd7ad987a38a3d7e3a1650246c93a394b9e))
- design spec for heater backend via peripheral_device_controller_base ([`79362fe`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/79362feecdfe6ec483d317931ba2bca5b4cb1538))
- consolidate project docs under src/docs/ ([`00b0aba`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/00b0abad4aacc487eec66088b8b69e85197718b1))
- **#477**: implementation plan for guaranteed-loop duration mode ([`764ad98`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/764ad9859f5a9f1e424c73e6fc2ee6a5b15e1e1d))
- **#477**: spec for guaranteed-loop duration mode with unique-phase navigation ([`636341e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/636341e8a97a325ed080e2e508720e8a107c77f8))
- **#477**: implementation plan for guaranteed-loop duration mode ([`dc8d3b4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dc8d3b40de0b5bee23a258306f61ffd1ede2534c))
- **#477**: spec for guaranteed-loop duration mode with unique-phase navigation ([`d81c260`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d81c260888bc7e60c3be7fa4c4f6476621122111))
- **readme**: document --plugins usage for the run launcher ([`21a7100`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/21a7100185effdd0c396b35046167f43a9675644))
- spec for persisting device-view rotation ([`653a37d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/653a37db114aa1294dcf673028738fd1677b7c3f))

### Test

- **heater-plots**: cover disabled/revision/run-state model semantics ([`f1ccc28`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f1ccc28da17cd3d0081c326198e998b09d564495))
- **#415**: assert state messages don't carry id_to_channel ([`089cdc0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/089cdc0a59006de65ec1692e10d3e63d3c5ff92c))
- **#477**: exercise the loop branch in unit_cycle_len test (review fix) ([`a433d1b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a433d1b8e3da50feb2e9a4d344af5cccce8e925b))
- **#477**: exercise the loop branch in unit_cycle_len test (review fix) ([`ce6e43f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ce6e43f85a9f08bfa5ad33a0d501759d8bec8967))
- **protocol-tree**: cover column-visibility persistence ([`a08c660`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a08c660bf691397305ad3eb32f51e8049639117d))
- **message-prompt**: cover pause/resume/wait + handler guards ([`36e9c8b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/36e9c8bd6c63aaf575238e245ab281beba28360c))

### Chore

- **peripheral**: expose the ZStage SEARCHING signal topic ([`9a2c59a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a2c59aa9df36f74a49ad920e59f36fef54781ff))
- **heater_ui**: add standalone heater control app source ([`27278e3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/27278e339b6ffa855f3470bffff84ef046f5f77e))
- normalize Unicode arrows to ASCII in comments/docstrings ([`d851cce`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d851cce89f8c7a0d3f465bf1f930dd13fdc00933))
- **demo**: focus run_widget on the message-prompt column ([`8c0309b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8c0309bd07ce2c6e53b1253d76b1d4cfb510639d))
