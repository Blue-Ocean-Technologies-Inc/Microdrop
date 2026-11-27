## [v1.56.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.56.1) (2026-11-27)

### Fix

- **device-viewer**: save area scale when SVG lacks metadata ([`7c74e04`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7c74e04df337d253b5ed752db415ebf9001b1210))

## [v1.56.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.56.0) (2026-11-27)

### Feat

- **protocol**: bound Voltage/Frequency cells by the device range ([`d836446`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d8364460ededc6984fa8f38bb44a9062d5154f67))
- **backends**: publish protocol ranges from OpenDrop and the mock ([`64fddc9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/64fddc9d5a6f84d0e76065e8bf3c9fc1e9f3309b))
- **portable**: publish the portable's protocol setpoint range ([`bd3a47e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bd3a47ecd1786f154947dd5064675d1d62288a25))
- **dropbot**: publish the protocol voltage/frequency range ([`6f4f1e4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6f4f1e4a17a76aee1d815c39b92d3c7219e84849))
- **notifications**: title traits errors by exception ([`abaffcb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/abaffcba815e45f608ed8bb1aef0cfea1d490d89))
- **image-viewer**: report no experiments to prune in a card ([`a4f9c35`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a4f9c3526f1a59f0cadd854735be8831679ed29d))
- **image_viewer**: prune experiments in background ([`3b69376`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3b6937678cc315c3c435a655fc9776fbe26ea5c3))

### Fix

- **protocol**: treat typing in a clamped cell as an edit ([`ff11f57`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff11f57fa4e42522a5e85f595c9d95ccb8094568))
- **preflight**: check setpoints against the device range ([`37e0f70`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/37e0f70ba37ed1e7fe10c3dbc4c2794aaf968738))
- **protocol**: keep an out-of-range cell value on an unedited commit ([`5782d25`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5782d256e33ead23461685665337a6664f8f3678))
- **protocol**: clamp new steps' Voltage/Frequency into the device range ([`d8a68cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d8a68cf5c105f51d323b25ccc6204c4966025f05))
- **demos**: stop Redis only after the Pis shut down ([`8494b31`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8494b3148ffea1e98bedc93b5bf99d58b37832f7))
- **demos**: clean the Pi worktree before applying edits ([`70eec87`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/70eec879fd885122ef237a6ad28f2670c13966ff))
- **examples**: exit 1 when a headless backend fails to start ([`6e67438`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6e67438115f684781aa48446b48697063a5a07e1))
- **examples**: exit when a headless backend fails to start ([`e01c17f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e01c17f38873d41f988f7530ddb9823ca13353a7))
- **examples**: keep a headless backend's plugins running ([`c6a4709`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c6a47095251e90bd31ca84f62d2dd2de0f7c8f4e))
- **status-controls**: resync realtime icon on every backend echo ([`2b5bfe5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2b5bfe5de9601df26d175a8bb4a09f892dadac8f))
- **controllers**: publish realtime off when the board refuses it ([`e49e8dd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e49e8dde29809be6ddaeb0117d7179b19fa3413e))
- **controllers**: log handler failures once, in invoke_class_method ([`82c08cd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/82c08cd2c79f9ae947b30553772dada72fd41e96))
- **notifications**: keep the card when an exception's str fails ([`99a58b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99a58b8cf125e50c89964dc9852bef22cfc0ab35))
- **dramatiq**: log a handler failure once, with its topic ([`336a68c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/336a68c7f3cf8dd58d4b8d863579fa429f0a3049))
- **notifications**: read the exception line off the exception ([`b100001`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b100001cd0fef5e90735bf8498edb19d51079de6))
- **dramatiq**: log handler failures with traceback ([`a051779`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a05177999d354ada504eea1b52bcf8e7885d1048))
- **image_viewer**: report every prune outcome ([`a4f9bb9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a4f9bb9eee2ed634772b0fbd0c64c78f4b9df427))
- **protocol-tree**: repair run-logging manual test demo ([`53d19d0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/53d19d0e3db79bd07dae8702c7e57f8be34d3271))
- **protocol-tree**: list area and thickness in demo columns ([`5c452c0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5c452c03e66d43da7a23863514d9656763f18023))
- **protocol-tree**: log force in mN/m via force_for_step ([`6c64c01`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6c64c010760cd1da789a2bb2056e8af900c0f1dc))
- **image-viewer**: keep experiments whose read failed ([`b57882d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b57882dbb1c704790e1b881b0572bd32df796099))
- **image_viewer**: stop saving empty plotted experiments ([`6801053`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6801053e1a4b59934d2cfcdca5dd9e03d159ef3e))
- **device-viewer**: show Stop Recording tooltip while recording ([`9740ac1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9740ac13a385c52fdc92f0f8a913beb10d8b9279))
- **device-viewer**: fix device lock tooltip grammar ([`8e8ce75`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8e8ce75adb53f8d7f2270702fccdbd1094514a43))
- **device-viewer**: point endpoint warnings at Align Camera ([`802252c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/802252cbc6ba934d1d79b139ef3317c0310fdad0))
- **dropbot-controller**: set realtime mode after the board applies it ([`8a50a43`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8a50a431de36b179ead85acc6d4e38ec48abe7bb))
- **status**: stop writing the realtime key from status models ([`9697d01`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9697d01192c48d737ca3cfa33791085bbac32e09))
- **backends**: end realtime mode on DropBot and OpenDrop disconnect ([`4fd854d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4fd854dc1352eb8613413ef8c2ef98b1ae53ce27))
- **backends**: make the backend the realtime key's writer ([`8735813`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/873581335b4244bf8d38006f8c92de8dd6bd702b))
- **status**: stop resetting realtime key on build ([`e09509a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e09509a25e88b3306e66c571b29d717d618d5196))

### Refactor

- **backends**: write the default protocol range as a list ([`955c7a3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/955c7a34288b0815e1d1cd84a454ef0b926162cc))
- **dropbot**: write the protocol range from the limit observer ([`d2083a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d2083a76c323860e1de3aeae6855e75ff00e4341))
- **protocol**: share one guard for remembering the last setpoint ([`47857d5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/47857d52765a602fa3d327fca0f6c8f591054fa9))
- **dropbot**: write the protocol range from the hardware maxima ([`5044ad2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5044ad204c0f4462758699ba7f9fb77b6a4209b4))
- **protocol**: one default range constant per quantity ([`a050165`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a050165c5c6f54e4c1ceb6d2ecbcaee9fd813ae2))
- **demos**: make the Pi launcher and pixi paths options ([`fe60a10`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fe60a10ba3d7020dfd5aef4a18e66b47f7524c09))
- **demos**: drop personal defaults and harden shutdown ([`74995e5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74995e5a5bbaa75ae55ba0ac154e4f08a16f1918))
- ruff-format test_protocol_set_handlers.py ([`cf57e37`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cf57e378145d010f2280500dbb6f59974e7d0990))
- ruff-format dropbot_states_setting_mixin_service.py ([`668ca3e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/668ca3e9887260aa0442a23035bb012b5d2c84bf))
- **device-viewer**: record tooltip via method, fix docstring ([`14d6634`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/14d66348cc32bcc76c682bce6178ab256f1df9cc))
- ruff-format opendrop_controller/plugin.py ([`56ef024`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56ef02498e4a87c0681d65a61fd8e3590b956ebc))
- ruff-format opendrop_controller/opendrop_controller_base.py ([`bc16484`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc164842f40e9c06d73d0743985073dff5899cad))
- ruff-format mock_dropbot_controller/plugin.py ([`2415e8b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2415e8b4a2a0a8137b187097e1c24e2e58a6c6b7))
- ruff-format dropbot_controller/plugin.py ([`3971695`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3971695f6f1ad9b4bfff46380292c7cd72417cad))
- ruff-format dropbot_controller/services/dropbot_states_setting_mixin_service.py ([`bbc2853`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bbc28539298102533ace600df24f406779bd97d0))

### Docs

- **messages**: note the pre-flight reads the device range ([`5534ccc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5534ccc38603fad4635514d36a4ccb5726083e13))
- **messages**: update the protocol device-range flow ([`3af4d0b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3af4d0b43fda6f416f019d099bcff9d1c1b1043e))
- **portable**: document all re-exported DropBot contracts at once ([`c9ec4ec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9ec4ecc6595da85436169e802500db040e994f3))
- **messages**: document the protocol device-range keys ([`367d36a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/367d36a7502a2d91fe416186d135ffc72c08af70))
- describe background Prune Experiments ([`678a72e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/678a72e73fd68716a4744a941acde6280d7637cd))
- **protocol-tree**: update force column label and sample values ([`5896640`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/589664018ffb61699efd26c9ac9992c47d7a57ff))
- **device-viewer**: update camera tutorial UI texts ([`6cdd76a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6cdd76a1932a263943b847c61e8f5b9d97e9e1af))
- describe the backend-owned realtime key ([`7b7ee46`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b7ee464cb94fa278902ed20a3ea3eb27c8c606b))

### Test

- **controllers**: expect realtime off, never on, after a refusal ([`ae3b1cc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ae3b1ccfed3202ee86fa5ea585df6f76f896f6a0))
- **device-viewer**: expect handler failures via logger.exception ([`af6f624`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af6f6249f38eb1407e3e1af18ea97ae9e7c1a266))
- **image_viewer**: cover prune failures and skips ([`39e8c2f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/39e8c2f1d9cddc10514d58b8bed4a57f2fe8b7e5))
- **image_viewer**: run prune job inline in tests ([`af8dc7f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af8dc7f73e64e4e46ea339db1bf4d0d2a86feb87))
- **protocol-tree**: drop duplicated force check ([`305a09e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/305a09e4c28252f55f61fce497510daf8a517df6))
- **protocol-tree**: check logged force against force_for_step ([`2b91d30`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2b91d30a97c117df6e2ef0fda361695f6a6ddc57))
- **image-viewer**: cover which plotted experiments are kept ([`1871e2e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1871e2ee6207585f8895d20906cacfdc48b6cd84))
- cover the realtime key's single backend writer ([`f57b3a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f57b3a46fc2de9fc4ac020eb93023e18c53aaea3))

### Style

- make two backend controller bases ruff-clean ([`1180ea7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1180ea75d5a6ecdbbafbac6f592ba2fba24f98a3))

### Chore

- ruff-clean the voltage/frequency column tests ([`cf7ac89`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cf7ac89a0f8bb6aaa35f4f92b1f43a52dedc8033))
- ruff-clean files the device-range change touches ([`b1e1304`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b1e1304878e5b13ed4a8d49a1cb3b074a16adbb6))
- **demos**: drive portables from a laptop GUI ([`cc745a8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cc745a8d0bd6ea9adac706a14e43af1cb65d3912))
- **demos**: show the new handler-failure log in the sample ([`21581b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/21581b0db8d6c104e97dcbacf088817ea2df735a))

## [v1.55.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.55.0) (2026-11-27)

### Feat

- **message_router**: warn when another instance shares Redis ([`cc6042b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cc6042b06f3959a708d5f1583fd8abb97aa1d9bd))
- **preflight**: show the ack a run waits on, with a countdown ([`4d1076f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4d1076fb2b870e47fe7cebb32744f7831bd6087a))
- **execution**: carry the column and timeout of ack waits ([`4fc557b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4fc557b7e7d77d829aa4daea4b2adc6eb7168e93))
- **device_viewer**: count zone edits as unsaved device changes ([`7cf84c7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7cf84c713c7578129297b505f61f0790e87e66d9))
- **status-bar**: add a run-progress line along the top edge ([`204a7c9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/204a7c94ee238b129edf453558e63ca2a34f4702))
- **device-viewer**: show canvas hints in a pill over the canvas ([`88c6f7d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/88c6f7d937255d124e58e48a746150d083801b05))
- **self-tests**: warn of a disconnected DropBot in the drawer ([`910623c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/910623ca732f99490c963f8f3229ecb7ac54882c))

### Fix

- **self-tests**: end cleanly when no DropBot is connected ([`529bdeb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/529bdeb79813b11236413fe4c9fb0859388adad6))
- **self-tests**: honour a cancel in the report and the dialog ([`d6422c0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d6422c0da4d50763036c6de01323e908d913895f))
- **self-tests**: open the report browser out of process on Windows ([`07cc010`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/07cc010d4e808a2f6caf5490f3e897e06454e0c3))
- **pluggable_protocol_tree**: forward compound pre-flight checks ([`aef1bec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aef1bec69eb3c159c542f1f6c51645002480b017))

### Refactor

- **status-bar**: drop the unused centre message API ([`4e3b09b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e3b09b943ae9b62fc5416103689d2a2e5d28f3a))

## [v1.54.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.54.0) (2026-11-27)

### Feat

- **device-viewer**: device chip in the status bar ([`f9ae2f3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9ae2f3680f0368cd88cdb82236af12b8e850b02))
- **protocol-tree**: tinted pre-flight pill with paused state ([`f4136ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f4136ef82602d201aba48db351046f56fd5c09bd))
- **protocol-tree**: step navigator and protocol chip in the status bar ([`58c3d00`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/58c3d00f11f15f6a6873904a53dc67d42e28dceb))
- **utils**: shared status chip widget ([`80369c5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/80369c5f8254b7dbc15915b6f909795e127e08d1))
- **examples**: pre-flight check demo ([`4b9a45b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4b9a45bf8eed76096abc9600ae5cfd04dd42bd80))
- **dropbot-protocol**: DropBot pre-flight checks ([`5730f4b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5730f4b9d3d8afa165f8237f8af827a4c339d0a8))
- **protocol-tree**: gate runs on the pre-flight check ([`9448110`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/94481109e986ee4d3e5577453888a3c4092bf813))
- **protocol-tree**: preflight_checks column hook and preferences ([`83d06ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/83d06accbe5b57c30ac96080a901f358f71b9cb3))
- **protocol-tree**: pre-flight pill, card and settings views ([`3fccf45`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3fccf458c9697020f4bb14029b1f06caef85f95b))
- **protocol-tree**: pre-flight models, checks and controller ([`0169fcb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0169fcb76efe33ed4a30c68d9ffd2207d08f9b2f))
- **preferences**: open the preferences dialog on a given pane ([`5dbc23d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5dbc23d3660407d7354e0a46bcb9092c4544fd2d))
- **status-bar**: left-side slot for contributed widgets ([`86f0ecf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/86f0ecfd8e2906890a19a43eaa8374e0fbaa4e04))

### Fix

- **protocol-tree**: compact ack-wait face and rows that fit the card ([`4584beb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4584beb3984b9c2f6f57b49d6f9bf411c534db70))
- **mock-dropbot**: mirror DropBot state keys like the real backend ([`0e335f9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0e335f9db2c74a504533e32c7d3130a0a837def5))
- **dropbot**: keep connection, chip and power state current in app_globals ([`2e71a09`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e71a094075cdf40be85dc6e5842e89a535959ce))
- **device-viewer**: show every alpha table row ([`f0b162d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f0b162d4a6e72629f2a947bceceb09ee80ac7c73))
- **device-viewer**: keep the sidebar at its preferred width ([`912f3a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/912f3a4d0789f9aca2ee417b567853a6bb62ed13))
- **portable**: apply protocol step voltage and frequency ([`8314462`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/83144622e502a5b18fc6e8162fbcffedd798f829))
- **portable**: reject HV setpoints outside the supply bounds ([`40f6a5c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/40f6a5c105cc7496b52cc3003c3e02ddd057ddc7))
- **portable**: raise the voltage floor to 40 V ([`fbee539`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fbee53927a3f468b787dbe840ace96b0245f1eb7))

### Refactor

- **examples**: pre-flight demo uses the real status-bar widgets ([`4d40de0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4d40de02b3e015770015f19eccade78a93ca59b8))
- **status-bar**: left-slot priority and grouped widgets ([`7f3fa62`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7f3fa627e96c4cda5e52b0a8af51960893be2403))
- **protocol-tree**: drop the unused-columns notice dialog ([`00b4277`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/00b4277fef91adc58cbea8702e0ebecf86aea0dd))
- **style**: share drawer metrics in microdrop_style ([`284c0ca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/284c0ca50231e5dd2c94713dc82cda1bfa2ad34b))

### Docs

- **messages**: document pre-flight and DropBot state topics ([`d60ddaf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d60ddaf371489aa38d8f7b3ad998cd7a8fd0eff6))

### Chore

- Update Logo. ([`a124786`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a12478691137e5c77b7c55d4c019568784823bd4))

## [v1.53.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.53.0) (2026-11-26)

### Feat

- **notifications**: add a Sounds tab with the chime designer ([`18e06ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/18e06ac1b5ad7fa4cd20b03f8fc192c476fa8ca4))
- **notifications**: play chimes from the user's chime design ([`e7b1a0f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e7b1a0f0c0697cc5afa8422902e86b8fd9e801e0))
- **style**: add numpy chime synthesis for the designer ([`0452f44`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0452f4446c435d6417cd22cb7a2e7e872f25a3c0))
- **pluggable_protocol_tree**: chime when a protocol finishes ([`11c4080`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/11c40809378f3bd194889b30edbcd3601ab81930))
- **dropbot_status_and_controls**: notify chip inserted and removed ([`71a3727`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/71a3727a983817d776b4dafc566b85540b3068db))
- **dropbot_status_and_controls**: notify DropBot connect and disconnect ([`be8b0aa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/be8b0aa2c046dee6e3c677fff8119d8c938cd084))
- **microdrop_style**: lower, warmer notification chimes ([`5d53c89`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5d53c895eb1386e1e933f9d962c5e7ed0bf97624))

### Fix

- **notifications**: fall back to shipped chimes on any render error ([`f0fb7a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f0fb7a2c3803d48c787ec00e095b50b0e19c52ec))
- **plugin_management**: deepen the Plugins blue on light themes ([`323a3bb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/323a3bb4ede2b99710b1af02cb12a8af7f008464))
- **microdrop_application**: list the 290 px sidebar default ([`7f25966`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7f25966f4b79007b12061fb1d852f16a91011832))

## [v1.52.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.52.0) (2026-11-26)

### Feat

- **news**: list Announcements right below Top stories ([`918dc5f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/918dc5f539453297634ebf2ffcf7f4e51c2cda88))
- **news**: add an offer kind for sales and promotions ([`e984165`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e984165c7d8a37c058a8f7976318d4c0b74bfa48))
- **plugin_management**: flag a failed plugin on the Plugins header ([`68c0400`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/68c0400a88950bfbfb35dc75e320fa83b77265b6))
- **logger**: dump native-crash stacks beside the session log ([`68ada1d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/68ada1ddc89827d5a7202c04dcfabe98c4e10cd7))
- **news**: fold the feed's sub-sections with collapse or expand all ([`c5e9a69`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c5e9a69e7a5dcf8358e1f67924656110cfa3a800))
- **notifications**: collapse or expand every section from the header ([`167b7d0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/167b7d061976e330809761288021b114e153c3b1))
- **notifications**: let a section follow collapse or expand all ([`ce07b4c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ce07b4c95e7de7365a8fb84a1bc02828e0fd72ce))
- **style**: name the unfold_more and unfold_less glyphs ([`345b52e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/345b52ec5df4f46ce061c8fe26a4e50296aeca08))

### Fix

- **notifications**: give Announcements and Plugins distinct colours ([`07e1ec9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/07e1ec955292507319cf07b09ace995659e2d1c4))
- **electrode_controller**: clear channels even with realtime mode off ([`90a5e08`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/90a5e08f50085a2f7df290bc76a019355e33228c))
- **notifications**: keep every header button visible when narrow ([`714e988`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/714e98892e82bfa96316910c99c7658c1e9b355d))
- **device_viewer**: narrow the default sidebar to 290 px ([`54ff0ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54ff0ac1688ac4b4aee3bfa2f3a8814a295ea89e))
- **dropbot**: read hardware limits from the live proxy ([`734033d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/734033d9b3113e27d46d75fddf5f7432907c6703))
- **news**: fetch feed thumbnails over Schannel on Windows ([`86d9880`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/86d98804c61a23956c337eb346253d99d2d5e86d))

### Refactor

- **notifications**: move the reveal highlight to its own module ([`51b7674`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51b7674a9a8f6dd3f763093978d470fb05382636))

### CI

- stop the automatic Claude review on every PR ([`0b132ae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0b132ae5ecd6ca4965db5bb0769863b72397de07))

## [v1.51.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.51.0) (2026-11-25)

### Feat

- **notifications**: compact, scrolling settings window ([`bf10b9e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bf10b9ea0f97744468e32d6ff1641f3fa658cac2))
- **notifications**: fold the By-kind settings into sections ([`eeb3643`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eeb36430fb110ec079dca9c73ca7c245a5203ffd))
- **notifications**: keep the settings window's state for the session ([`821500a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/821500ae6aa454dbb3654f880a9e23276376e2fa))
- **notifications**: restore a kind's declared defaults ([`6ae974a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6ae974ac3c59dcf8687e4763a4b014170868e4a7))
- **news**: zoom and pan the picture preview ([`7f25aa0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7f25aa01ce784af02f4ccf962b2f3e0e55e438d1))
- **utils**: add a zoomable picture view ([`6f0ca7f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6f0ca7f3497522c2c8c9a8d0624d8b2e13b1d789))
- list each dialog-shown error once in the drawer ([`61263f5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/61263f513b06080ec33e9a7b75174935f48ecaa5))
- **pluggable_protocol_tree**: one drawer entry per dialog-shown error ([`037c189`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/037c1895db4fb0daa5695b0ecb432629f727c097))
- **pluggable_protocol_tree**: leave a card for every run report ([`8221b46`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8221b466f082e76f046ce1779deed53da43df506))
- **microdrop_utils**: record a failed action's dialog under its plugin ([`0c993bf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0c993bfd68d74edc15992efa34d9b20ad53f097f))
- **portable_dropbot_status_and_controls**: name the alert dialogs' source ([`2990bae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2990bae4db3af1c6b9a1014a5a32a601a75684e8))
- **dropbot_status_and_controls**: list halts and no power in the drawer ([`745ebfd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/745ebfd3db49672cc2f7a02e81104183bfd8f88c))
- **notifications**: let a thumbnail click repeat a card's action ([`c56a58d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c56a58d5807f4b87d2deafd9bc99574d636bec6d))
- **dialogs**: record error and warning dialogs in the drawer ([`d37ab71`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d37ab71916fc110a25f7fc3fa3af1ae5747aca0b))
- **notifications**: make detail links clickable in toasts ([`0856450`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0856450326bf442bcffd930b0e140045b8f193a2))
- **notifications**: key posts by occurrence and skip recorded logs ([`fff460f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fff460f887e6acfdc83062b98bbba0fcbb88a46a))
- **notifications**: add occurrences, a dialog category and a log marker ([`ec81bb3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ec81bb3ec535e81f471268e02ce99b066c4dcd7f))
- **device_viewer**: give capture cards a thumbnail and file link ([`7b54f5b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b54f5bdaa3424ce39588dc5f91c136fb03ee38f))
- **notifications**: show a card's thumbnail and detail links ([`158263b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/158263b572145b89ec0b23aa6f313245e79217fb))
- **microdrop_utils**: add off-thread thumbnails and label links ([`7a9bb53`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7a9bb534b891a7bd2e2b56fe2a49b3dd8f9f1c72))
- **notifications**: add an optional thumbnail and detail links ([`9f67f31`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9f67f31a4d80ff2ec9e79a19c4a24b22125722f4))
- **device_viewer**: show captures in their viewer from the cards ([`6290eb1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6290eb16151dfff5300337552b3a3004ff381458))
- **device_viewer**: play a recording on request (SHOW_RECORDING) ([`8c6c894`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8c6c89416655cc47e5d86c503250a045e0d98cc9))
- **image_viewer**: show an image on request (SHOW_IMAGE) ([`3cf8d29`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3cf8d2947f6859d74223de04f4bc6c9a09650967))
- **microdrop_utils**: bring a dock pane forward, raised or popped out ([`b64a3ad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b64a3ad6350e764668172351fd921a4fc1ccabf5))
- **device_viewer**: post photos and videos as notification cards ([`fea1189`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fea1189378b82d898b0badc7735f225887316c77))
- **device_viewer**: declare the Camera > Captures notification kind ([`a196661`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a1966616c96e0bfcfcfaa5210008548d67c05cfd))
- **notifications**: build News first in the start-up drawer ([`a15acba`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a15acba2a305bbff26b03377b18f953dc93ba076))
- **news**: show the top story before the other sub-sections ([`9a0f83b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a0f83b91a08ae53b4aec10af206b83d9e501eaf))
- **news**: decode feed pictures off the GUI thread ([`c25d161`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c25d1619726cd05501c9302009937605759b90d3))
- **news**: read the feed off the GUI thread at launch ([`6d5548c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d5548cb42107784c44464613c3ac19bf76c2e30))
- **plugin_management**: load the News plugin first after launch ([`36cf95f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/36cf95f668453d518d1c9adad2d548a56e11ab6c))
- **notifications**: let an app-opened drawer pass a click through ([`7a2e6fa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7a2e6fa17ad83ad1deabb0921d36ec8528931bae))
- **notifications**: lead the start-up drawer with News ([`7d26905`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7d26905085c32376357e5f83d132ba22617ba624))
- **notifications**: open the drawer at start-up ([`50ed48e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/50ed48e7986380a420673f80830eb340b5b14aea))
- **notifications**: save the notification settings ([`a63e888`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a63e8886f434f71ad3fe3ae74c17bcb6cad53efc))
- **notifications**: let the app open the drawer without the focus ([`05b9c14`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/05b9c146e5c042037eaa29689f25c6fcdf1096dd))
- **news**: rename the Dispense and Releases sub-sections ([`4dcdefa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4dcdefab7d8e2a3537990b57a08e04c5143427a8))
- **dropbot_status_and_controls**: point help links at tutorial sections ([`13d76ea`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/13d76ea728c5dafe97fbf039170155a396a91c44))
- **notifications**: open a card's tutorial from its help link ([`add308e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/add308efcbb38ace58958e8ef34b0c8d6a78f57d))
- **user_help_plugin**: open a tutorial by id from anywhere ([`2cbb008`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2cbb0084050affdae3b37747e8368c6443d0f52b))
- **dropbot_tools_menu**: run the self test from its reminder card ([`bb9c177`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bb9c17770ec648399fb02007f78433974171eb5c))
- **dropbot_tools_menu**: remind to run the self test when never or long ago ([`4e35b44`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e35b444e321b711e7a7d86fdc718fa9a771eafb))
- **device_viewer**: remind to calibrate when none is saved or it is old ([`c9f2580`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9f2580f2de9bdba5ce90c1b3729895a157d4b5e))
- **notifications**: keep the feature's state in one data folder ([`6c2fa3b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6c2fa3b1955d6dc3fccb7228d2436a5511cde9d9))
- **notifications**: let a sender post quietly and rank Needs attention ([`f45decd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f45decdcfcf6b8046577c2d5f45c7c91b4813575))
- **examples**: let the notifications demo run at a larger app font ([`c210f5a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c210f5a93b588a70e67a1ea58460e48cc1c2bb98))
- **notifications**: isolate the panel's look from the application's ([`a0f5110`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a0f5110d4ce157079cad30b2749ccadfda45386f))
- **news**: describe the chip top plates offer in full ([`d1a8edb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d1a8edb0832ff21f0a2bf5662086a53e58a923ff))
- **news**: add the chip top plates offer ([`b898ba2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b898ba238d82dd277ccd558616014d9c4c1fe30c))
- **news**: add the DropBot v4.0 top story ([`54698bf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54698bf00e88afce71586da2e5dd152e84589495))
- **examples**: load the news plugin after the window paints ([`a40cc7e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a40cc7ed4c1ea48a773592de2c1fc11c8d46d1d8))
- **microdrop_application**: leave the release notes to the news plugin ([`417ad05`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/417ad05abe54d47115bdd1dade5f412fed69cead))
- **news**: add the news plugin, the News section of the drawer ([`75fa805`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/75fa805c84a9d96efb7cc236b09e8b5ac3d26a3d))
- **notifications**: let a section alert stay quiet or sum up others ([`5b15f23`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5b15f239820556dea538497dd27a912f0b9f5db8))
- **microdrop_style**: use the marks-only Blue Ocean and Sci-Bots logo ([`6c22236`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6c22236e51a0a00625ba330e90c9a8648bfbd4fe))
- **device_viewer**: post camera alignment restores as notifications ([`52a787d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/52a787d8be712067ce2dd6f13c8e8aa2982a2be8))
- **examples**: add the notifications Demo menu on MICRODROP_NOTIFICATIONS_DEMO=1 ([`2e3c98f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e3c98fb14380d984503cebca30c8e7bf04c11ab))
- **plugin_management**: give the Plugins section its glyph and accent ([`f7da907`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f7da907df09aa8d149aea771692ae661f2e329df))
- **notifications**: drawer column, cards, toasts, bell and chime ([`0fc3146`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0fc31464b507df3f28c7a09473764bacc7b48143))
- **notifications**: actionable, threaded, resolvable notifications ([`2120cfc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2120cfc7c4d9f29f349088eff59d516c6e439d47))
- **microdrop_utils**: add clamped and elided labels, item view fitting ([`2198c9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2198c9b116a99d5abd365190d59d834cc728837c))
- **microdrop_style**: add colour contrast and palette helpers ([`ad59fcb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ad59fcba6e5fef37c85187fc6e075a0d40032e3d))
- **examples**: colour the drawer by role, quiet titles by default ([`ca5bf51`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ca5bf519e49b724bdaefe5d53361f776e9414c04))
- **examples**: give the category accents both themes ([`cf6f8af`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cf6f8afbe6bec43efb63af80e2ed71ce36c61453))
- **examples**: add the drawer's colour roles ([`7c0cb12`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7c0cb12aadd49c90f43bd4330e5b1e8c7a494329))
- **examples**: give every drawer header its own accent ([`0745bf6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0745bf6051d5e4d2dd1247688074d67c67ef3456))
- **examples**: colour Activity's filter chips by kind ([`a7544af`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a7544afbab4acb3d40f309605d0601e14332bf13))
- **microdrop_style**: add gold and teal accent hues ([`b154487`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b15448786bc4a8d0f517bf71c142693c77626265))
- **examples**: notify DropBot connection and chip changes ([`3728559`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3728559f58bb33569e5aefa7a7f83f6ea63eedc8))
- **examples**: play the connected and disconnected tones ([`13ab636`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/13ab63604ad397870208e846d77e1fa463027358))
- **examples**: let a thread's post replace its entry's state ([`01cea16`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/01cea169cfc2124402f55ed5f6a7556bbd197beb))
- **microdrop_style**: add the connected and disconnected chimes ([`7ecc2c7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7ecc2c7e48d2281673981c8c74e1d10ea290c676))
- **microdrop_style**: ship the Orbitron and Lato brand fonts ([`f1f6dec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f1f6decab4afe999f423900160c7d34089bc5fce))
- **examples**: set the drawer's text by its type roles ([`e5bf88e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e5bf88e4ab14ec4c5fd8eee576ac52e5410b0d46))
- **examples**: use the brand greens for News ([`c1f06d2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1f06d2d040050aec8d6d4111e4f975b0a4de80e))
- **examples**: add the drawer's type roles ([`783bfd3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/783bfd3b92f722fc2db9d46c40fd6c89244f1c06))
- **microdrop_style**: load the brand fonts, falling back ([`0416ff6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0416ff666bde0b129e3af64d2ea0538b3e4f2e42))
- **microdrop_style**: name the Sci-Bots brand colours ([`4aad8f0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4aad8f09ef5ea0c683f7a101c5d5d7d3831aed3f))
- **examples**: merge local-only posts into the demo feed ([`212fc3c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/212fc3c7e69619dcc97ab6bd1fc35550f1d6327b))
- **examples**: show a lead card's two pictures side by side ([`c46a27c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c46a27cdc080d6c4c76dbd3b277ff329c5827c86))
- **examples**: let a feed post carry two captioned pictures ([`4c791c3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4c791c3e13fcba08d2bf6c0f2f5b5f87ad5b6b85))
- **examples**: give Activity a history glyph ([`cdca578`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cdca578608deb555ce05f756baae04f38d2c4ed0))
- **examples**: fit the drawer's height to its contents ([`c9e58e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9e58e8ba820c8fa3c2127aaa8bc39862a69235a))
- **examples**: add per-category notification settings ([`475da34`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/475da348262a553c1a9fb94bd5c278cb46a3419e))
- **examples**: chime as the notifications bell rings ([`3e9e534`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3e9e534c91c7a29cf1231254dbaefc71604e5d6c))
- **microdrop_style**: add synthesised notification chimes ([`f333bae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f333baecc8dfdaa9a040f6a076c244bee2d35ccf))
- **examples**: make the chip card guidance-only ([`43a95de`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/43a95de2d5b08df43fc6d6f76bad15a8d8f37766))
- **examples**: resolve attention cards when their condition clears ([`4053dd9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4053dd9e5197d100471e21985e8a977c8e619ab1))
- **examples**: add a stale self test card ([`1af3477`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1af3477ec710694432e8b1375c70849e5c748af1))
- **examples**: show help as a card's one control ([`995c19e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/995c19eb85d46347c04abcc2caa3a0358d5a7026))
- **examples**: mark What's new with the MicroDrop logo ([`823abdf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/823abdfb1a2de49da2e8fed2c54c7b8bf4758046))
- **microdrop_style**: name the MicroDrop mark ([`7d8ea1c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7d8ea1c0a8d2f4dd65ae7e792b1bb06fd7048bb3))
- **examples**: title the catch-all feed group Updates ([`af61e89`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af61e89a24e6b5c726367de4222500f89d8abc89))
- **microdrop_style**: add the Blue Ocean and Sci-Bots joint logo ([`8a5a892`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8a5a892a6d6466da53b5f5b450e816ee3c23053b))
- **examples**: show one news section per publisher ([`ca30d1c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ca30d1c820582a942a93d4371f4ba7346aa759a3))
- **examples**: add a placeholder Blue Ocean news feed ([`ba6fb47`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ba6fb479ee5e718024eb928e25480179f561f1a9))
- **examples**: shorten the feed's group titles ([`870bd9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/870bd9b3a1b7b8719c7f9eff2b07ca1ed4c8bf74))
- **examples**: name the feed section News, with Sci-Bots mark ([`cd669c0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cd669c0c1879b3720579e6b72d67628ec39228a0))
- **examples**: give feed sub-headers the feed's own look ([`3683123`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/36831235c1edf35c7aa1e16874f439c586958d54))
- **examples**: show feed groups as collapsible sub-sections ([`25c0387`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/25c0387896287f3bfc1a237e29483fb8aaf918f0))
- **examples**: alert on new Sci-Bots Feed posts ([`92e5fde`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/92e5fde0e8543bdc79b11ed2919d7bffeae1e81c))
- **examples**: add layout switch and protocol run to Demo ([`970f2d9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/970f2d99d5fa7e2bd9d2103c586494bb4ffd92ed))
- **examples**: show the drawer as one scrolling column ([`51053fe`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51053fe886d1572f1640acb114d0918fc02ef516))
- **examples**: add layout, filter, reveal and quiet state ([`2275d9e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2275d9eba678409ac6e1e0aa5a3e7df8f141a740))
- **examples**: make toast auto-timeout a setting ([`409e94f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/409e94f5d8af12aec67050e37bb3c9026e281651))
- **examples**: put the feed creator in the Demo menu ([`8edd504`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8edd504dae6813904440c3bfb7208d725c542424))
- **examples**: show a device SVG in the stand-in viewer ([`c158a5e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c158a5efc48fdfa734187156faa5d81a188c62e2))
- **examples**: run notifications UX prototype in the app shell ([`74d0120`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74d01208de80f92c4553206d6982b0af26bb14b1))
- **examples**: add notifications UX prototype views ([`3c66cf1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3c66cf1b75ea143116f692fdee9a3ddd10540696))
- **examples**: add notifications UX prototype models ([`23db35a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/23db35af2afe883e2a7239d35f90aeb48da0d992))
- **examples**: add a Sci-Bots Feed and feed creator demo ([`4d88180`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4d88180f2bb71c67b0736c045cf5c649cd44934b))
- **notifications**: let a section set its own max height ([`74ac221`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74ac22161fa4f3208ca3bd01f01634b526cb164b))

### Fix

- **notifications**: stop the settings window crashing the app ([`7879d01`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7879d015f9e437f19ea11b09ef665a1c53f4179a))
- **dropbot_status_and_controls**: create the message listener at plugin start ([`0166746`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0166746a02e9d492e141b16142ab7b2af41c423e))
- **pluggable_protocol_tree**: skip the end-of-run clear offline ([`f9b7e4f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9b7e4fca7107bba5a7285c306d42d90ed2c4831))
- **pluggable_protocol_tree**: log the sync's actuation refusal at info ([`160bd9f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/160bd9f8911bd69de919a78c62477f1d888fed22))
- **device_viewer**: post the calibration reminder after paint ([`67399fd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/67399fdbd1e87d6fea2eb672ca2cda64ddee0df0))
- **dialogs**: keep plain text and cut details at the limit ([`ebe44e0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ebe44e013092564e1462595cbf24a708ab253da9))
- **dropbot_controller**: list a halt or no power once in the drawer ([`e352e88`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e352e88dd1ba41bb32e89a019eea27801664ebab))
- **notifications**: open calibration help at Getting Started ([`d6eda9c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d6eda9c5a41aa6f711bee67683b04e2757a11e48))
- **pluggable_protocol_tree**: skip the end-of-run clear offline ([`ce1a7bc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ce1a7bc1a073f61247e2b0f76bd759619f5fddae))
- **pluggable_protocol_tree**: log the sync's actuation refusal at info ([`b4a1fce`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4a1fce4cb7043b0bfc840e327ee354df0ce4023))
- **notifications**: keep Needs attention ahead of News ([`d8e5cad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d8e5cade462e077bdb6077d6d906a419c94040c2))
- **notifications**: add late sections to the open drawer in place ([`4f42b7f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f42b7f83e736a3bb262b9a01b11f02bbe01a374))
- **notifications**: keep Needs attention on the bell until resolved ([`9a6e6f8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a6e6f81b8643d16c06e1cf84943e356fdf9058a))
- **device_viewer**: log refused actuation at info with its reasons ([`71088a6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/71088a6c44dd06767bc924aebf9a6c1dca6f7213))
- **dropbot_status_and_controls**: create the message listener at plugin start ([`18c8bef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/18c8befcb814c82f196f7d9383f23a19d9152adf))
- **microdrop_application**: ask the plugin manager for the news plugin ([`a4a7e02`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a4a7e021d33b6e17d76574c966fbe7306950c875))
- **news**: fill the card's width with every picture, never pad it ([`7046782`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7046782542c59e43e9fc7b461dc900bbe06811db))
- **notifications**: measure sections and news cards at their width ([`9b181e7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9b181e7af7538b65d96b1c07762761d0ead9dc53))
- **microdrop_style**: give the drawer's type roles their own family ([`abaa3ff`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/abaa3ffc9c2eb33d8f8924bf1eed8800489af6da))
- **notifications**: keep the drawer's fixed 320 px least width ([`b9f9f86`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b9f9f86cd7ed57a5deb2562aaf17e78b6860985b))
- **microdrop_utils**: never fit a table's own headers ([`747a0fa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/747a0fad523e5ca7765f85a4bd14df0f236ed1f5))
- **notifications**: let the drawer narrow again; fold buttons, not the title ([`e4484db`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e4484db35e6104cc57ee7177fa0bec4d4b598b20))
- **news**: keep both pictures of a stacked pair, each whole ([`093aef4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/093aef47c532045b0cbed7b279d150b1d601b75e))
- **news**: show a lead card's picture whole, at its own aspect ([`e58e427`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e58e42785f8ea0959ab3e6d0599e6df84b55657a))
- **notifications**: never clip the drawer's title; size its least width ([`d54b63c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d54b63c2cf3f7a2ea9a09195cb4d415648fa803d))
- **plugin_management**: list every plugin in the drawer's Plugins section ([`914cc36`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/914cc368cffffd67cd32b515908b1188c947f5c0))
- **microdrop_utils**: refit item views when their rows change by layout ([`65f2885`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/65f288570c627c71a4bd9cae4449fcbc0902d82e))
- **notifications**: ignore deferred plugin failures the load status reports ([`9c37e93`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9c37e93ab90a34ab81ed6ad37556dbaeed1f6499))
- **device_viewer**: log the state-message pause and resume at debug ([`4d62911`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4d629119b1ae854a4a597bc337abead33b70a93d))
- **dropbot_controller**: report no DropBot connected as info, not error ([`a2b354a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a2b354a5f114d7e410ae00a8a82ae69851447ac9))
- **microdrop_application**: log Application Initialized at info ([`39c4df2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/39c4df266d1f9a7579677090b1c822f571d454f4))
- **pluggable_protocol_tree**: skip an empty device viewer state quietly ([`6d25f7a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d25f7ad0a68e7425afff5d19ab3bdb64c2d2419))
- **microdrop_utils**: raise DeviceNotFoundError when no device is connected ([`91bccf8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/91bccf8ecf48a3f97214e66340f9140e230ecfae))
- **device_viewer**: log start-up order and expected state below warning ([`d87a580`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d87a580c6a98fbe2f7c8066c8d1f46e622ef2280))
- **device_viewer**: sync the volume estimate only once calibration exists ([`0ba2dc9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0ba2dc95b1ee9d815fdc0e58a764ccbc2832ce7c))
- **examples**: firmer light-theme colours ([`a7bae70`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a7bae708b4d6908fd892249a04818996297df458))
- **examples**: rebuild a failing chime instead of going silent ([`bd0fd72`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bd0fd7283d803224bbf7d649c6b4520f095232cc))
- **examples**: rebuild the drawer's contents on a theme change ([`8c503c9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8c503c9594f156624975928550a79824b423cb88))
- **microdrop_style**: keep a forced light scheme light on a dark system ([`662fed9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/662fed9ef21f1247a299da1faaaaa0b3c79e141f))
- **examples**: one pill shape for every drawer chip ([`4a4a298`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4a4a2980174c797864c02cb582d508e4179a0e75))
- **examples**: chime for a repeated notification too ([`f1077ed`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f1077ed163c4e0a5c400fd16709e897a31d28756))
- **examples**: make the chime predictable and observable ([`ab4c0ae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ab4c0aeacc787890e8a1a60074a31811bed031aa))
- **examples**: give every pop-up category a tone ([`c97185b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c97185b59e0cb46c7ea8c073aab96ecdf5fec322))
- **microdrop_style**: lead the chimes in and let them ring longer ([`bbebe19`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bbebe19e2b8a7e91c3a7973fff43812b943d1958))
- **examples**: elide a sub-header's title after its detail ([`264c52b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/264c52b6388668cf3100e94b446e50355a8a4bca))
- **examples**: tune the drawer's type roles to the real fonts ([`f7a808f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f7a808fbfe69bd6ff4a03c2fea3448f9e33e4616))
- **examples**: end collapsed feed summaries on a whole line ([`ff9741d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff9741d9d5f523536fd398de353a9d2b04669ab8))
- **examples**: size a lead card's pictures from its width ([`0bf94d5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0bf94d5fc3e820709dfa5a8ae70a764c16cc44c7))
- **microdrop_style**: normalise the chimes' level ([`85c735d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/85c735df3f73469b0ace985106b726544cc538eb))
- **examples**: keep card button labels whole ([`c173697`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c173697c4c8c01c0db050950955c562b58e87c6f))
- **examples**: drop the contradicting Calibration done sample ([`515756c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/515756c5b03331b9e764fb02ccfd1b4931af3f7f))
- **examples**: drop the calibration card's Calibrate button ([`a8ada5e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a8ada5e989fa348b7a1e26dbb560952d9de634ca))
- **examples**: lay News sub-headers out on one row ([`26efb94`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/26efb94cd6d2d2374218c2fb8f3c32888383e509))
- **examples**: let the prototype's panes fill the window ([`a36456a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a36456a712e3b91e80dba37a6a14946c943a671d))

### Refactor

- **news**: remove the feed creator tool ([`6ed9d05`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6ed9d051f1a492c1493281a0ad48fc201c35726a))
- **examples**: run the notifications demos on the news plugin ([`062cbb6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/062cbb6474a81f253ab285d6b9cd091f5b5734ad))
- **microdrop_style**: share the drawer's type and colour roles ([`e58094a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e58094aa81e5f3610ae81967995323445880dc5d))
- **examples**: run the notifications demo on the product plugin ([`c40d66b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c40d66b6eca10565dcb470bd90b9d58a170ba040))
- **examples**: set the drawer's type roles in the app font ([`505c1e7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/505c1e7d0f3a9ecd11279c73dc8c7413da20bb4b))
- **examples**: combine the news feeds into one News ([`03e3b3a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/03e3b3a583e9fdddad1ab9acd4f8614f8923d5cb))
- **examples**: drop the resizable-sections drawer layout ([`65550c6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/65550c64d4ca5e72fba97bafe7d86fd71a5f99ad))

### Docs

- **messages**: document dialogs and run reports in the drawer ([`aeecea8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aeecea82236b905e879bd5dc4fe90f7ea49a5092))
- **messages**: document notification thumbnails and detail links ([`a0fc6d1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a0fc6d17c6b0172ddea31492c198e485646db29c))
- **messages**: add SHOW_IMAGE, SHOW_RECORDING and the cards' Show ([`62bc0b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/62bc0b090d4f83900216569190b459ab1cf2cd85))
- **user_help_plugin**: capacitance calibration as its own chapter ([`68c107a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/68c107a3abb9373b1dd05b8e73c5bd7b7fe3abb8))
- **messages**: add the camera captures notification flow ([`8acd9db`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8acd9dbffc7f39d387ad62239f1feb4cef0a9e60))
- **messages**: trace the calibration and self-test reminders ([`54977e7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54977e72757351a9f12e75b74af400d5b5cc8d8b))
- **messages**: notifications resolve topic, message fields and flows ([`1cd2874`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1cd2874888eb4747472209fdb19f6bddeb9475e0))

### Test

- **notifications**: build the settings window headless ([`223d9bf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/223d9bf9ca13c423b43d5a2006f5a4a087659587))
- **user_help_plugin**: start the Help plugin without Redis ([`fb9d2ec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fb9d2ecb5924b60d55153bbb90673c73849af925))
- **plugin_management**: check the Plugins section's table ([`31a27df`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/31a27df07440709128b16b474199eb56a25c2323))
- **news**: the shipped feed holds the top story and the offer ([`0ba6768`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0ba6768c9fec49f91e83cc7455ffd51a3b4cce8f))
- **examples**: notifications launch modules stay light ([`1548cd5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1548cd56b1e91cbbe7d71205b74d1c1822d9153b))
- **notifications**: contract tests; prototype tests moved in ([`3c8c22f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3c8c22f06328479b5da4316d54d9a4b0a6e9b04d))
- **examples**: cover what an arrival rings for ([`f0d3fb4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f0d3fb400071e3b201ce72ffaa08878775ea834f))
- **examples**: cover the picture pair's cell sizes ([`230c767`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/230c7670b3f060b01ec832aabd5da1f2bf0ca394))

### Chore

- **examples**: log the chime's playback at debug level ([`44c4e28`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/44c4e287c586c1f0aaa347aa8f09df9c60285b59))

### Revert

- **microdrop_style**: drop the brand colour names ([`a93dc3b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a93dc3bfb645f1e875eff8ad9f1f9aa43fb813e8))
- **examples**: use the prototype's own greens for News ([`3a5c420`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3a5c420a1687b5f8c2be7403f379ffce20fbe646))
- **microdrop_style**: drop the brand font loader ([`079ca08`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/079ca0808751be46389f1031f56530f78ed92194))
- **microdrop_style**: drop the Orbitron and Lato fonts ([`a84d0ec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a84d0ec98888736480400e4307bda03f3f8c8728))

## [v1.50.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.50.0) (2026-11-24)

### Feat

- **portable**: Clear Alarms button in the status pane ([`bd86534`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bd86534ad0a77beea28c82a737cc2bdeda7d0087))
- **portable**: clear latched board alarms on request ([`4943e50`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4943e50a2b7846da4b4b7d1c48e916f58d42ee57))
- **portable**: live plot and Verify in the heater auto-tune panel ([`6a2c27a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6a2c27a29bfa1ab1838914b832e69c926920a085))
- **portable**: heater auto-tune verify run ([`7614f9c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7614f9c33a0da8d48956d5cdec0b85fa3da7706c))
- **self-tests**: include board diagnostics in saved reports ([`13eedf0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/13eedf068fe05c8e930ce6a4fabe112cbebaf385))

### Fix

- **dialogs**: use pyface's "save as" action for save dialogs ([`ed2019c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ed2019c53593e7789f12ae0649e2c54a6b1b15ca))
- **utils**: let the mouse wheel scroll past matplotlib plots ([`c1f9b3b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1f9b3b105a95779bca2b5076112f6bd35e743fa))
- **portable**: restore motor param field after a declined confirm ([`8abc4b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8abc4b087865277ab0d733014104a7ef54856c2a))

## [v1.49.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.49.0) (2026-11-24)

### Feat

- **notifications**: show notifications in a fixed right-hand drawer ([`67be01e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/67be01ebf59fb42799ad58c38e7dfb40d7259508))
- **plugin-management**: show plugin loading in the notifications pane ([`0bf530b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0bf530b80e5a9681cea517702d092bfdf439dacc))
- **notifications**: add the notifications pane and status-bar bell ([`f1a57bf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f1a57bf5ae96416e93cb86557da52746d49f7096))
- **notifications**: add the notification model, topics and log feed ([`bb19134`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bb19134b8e1d97a6b7661122e2743dd1ebe3b673))
- **style**: add notification glyphs and a rightmost status-bar slot ([`2ad3202`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2ad32022b64e3805c8c1424080c86b9296ddf1dc))

### Fix

- **device_viewer**: drop the stray Group tabs in camera properties ([`eb7e3a5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eb7e3a5753bf5b7f11fff7df33820f1fb9131ecb))

### Perf

- **device-viewer**: build the device viewer pane on first show ([`7781006`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7781006cc9dc549ffaa929fae620015c300f713b))

### Docs

- **messages**: describe the notifications drawer ([`3776810`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3776810d398ac3f2035af9662fb9fb723c05e9d6))
- **messages**: document the notifications topics ([`0ba2af6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0ba2af6dc23d34b917419561d6c4897993500c61))
- **examples**: add a notifications pane demo ([`5c9d73b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5c9d73b261cddb72d64f970c44dc1bf7f0f30895))

### Test

- load pydantic fully before Qt in pytest runs ([`f129ee8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f129ee8ebfc7ad3f6be7eacddbb4f527ffe07475))
- **image_viewer**: wait for the ROI table, not a fixed second ([`dd2849e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dd2849e5db0f3fd223cbf799a927766d20b3278d))

### Chore

- **examples**: register the notifications plugin ([`91f5725`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/91f57252a0d046194e297947485206b06b9326fd))

## [v1.48.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.48.0) (2026-11-24)

### Feat

- **utils**: build dock pane contents on first show ([`9f5598c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9f5598c3fbc3d42999ea711e964797bcc2878f7d))
- **utils**: add a shared paced queue for deferred GUI work ([`d0a0897`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d0a08970b9c4fdd8809f143d3a597d4b680ece02))
- **device-viewer**: add sidebar sections built after first paint ([`7b2118a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b2118af6c4046c9f87fe94b1a76a851544364e4))
- **protocol_tree**: follow quick actions contributed later ([`7292394`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/72923945af15eb8eac3fcbe4a3fc89666f1c6c34))
- **launch**: load deferred plugins after the main window paints ([`eaf92a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eaf92a78c09855c6e3d8690218717cb1ca3c7c4d))
- **tasks**: replace a mounted dock pane in place, without flicker ([`0ff79b4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0ff79b4aeb3a7f7c4cec17ca5ce3a7233c85e5a7))
- **plugin_management**: show plugin load status in the status bar ([`58fb280`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/58fb2802a8d70e7e5833c9199e0e16bc5fc1d2e2))
- **launch**: start plugins one at a time and isolate failures ([`653fcdc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/653fcdc307c6c5adce4a98197762f1325d18286b))
- **portable_dropbot_self_tests**: board diagnostics ([`b78d951`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b78d95181214c912f154f3fd4f0e16569336f4bd))
- **portable_dropbot_controller**: board diagnostics read ([`33c348d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/33c348db96864e76aa94b13a9b42cd26f04d3033))
- **portable_dropbot_self_tests**: health test rows ([`af892ae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af892ae4aa9dffb88d87b21398a5e9de1a882d56))
- **portable_dropbot_controller**: self-test heaters off ([`9f753a5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9f753a5a4aae9eb3beccf671c9781df3aabb2a2c))
- **portable_dropbot_controller**: accept the health tests ([`f210d9c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f210d9cd6158955868d2550722cd85f70e8fe28f))
- **portable_dropbot_status_and_controls**: heater auto-tune ([`54918e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54918e119caa6c73db1e2eefdb732123594f94e2))
- **portable_dropbot_controller**: run heater auto-tune ([`176e74d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/176e74d99d33e0dadacb9d9474c26c3dc4fa2aa4))
- **portable_dropbot_controller**: heater tune contracts ([`6135415`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/613541553354c3910651e1bcaa2474e2b714897e))
- **portable_dropbot_status_and_controls**: heater 2 ([`5a2550d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5a2550d6a6142817907bba4ab96299f9cd47f3ad))
- **portable_dropbot_controller**: status events ([`a72fd0c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a72fd0c029e1e22bebb9f0ee43b8f88022784a28))
- **portable_dropbot_self_tests**: dark-mode plots ([`8946cc0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8946cc0ecc39656656a102178cd053e081883c6b))
- **portable_dropbot_self_tests**: run opens Report ([`1e9fe0b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1e9fe0baac6ae344d17e54dca18c81e41aca0051))
- **portable_dropbot_self_tests**: tray in or out ([`fca5ccc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fca5cccc8977c536e0f1ea93d590c8b26837395d))
- **portable_dropbot_controller**: tray in or out ([`812088a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/812088af590f36ebc0a0d3077da0ef06779abbef))
- **examples**: register the portable self-test hub ([`316e8b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/316e8b80de1066f192adc2e36821a8363cd3d82d))
- **portable_dropbot_self_tests**: add the self-test hub panel ([`2981bfd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2981bfdc852ff4b1adf320a4729ba6919db84f59))
- **microdrop_utils**: add figure and markdown editors ([`84ce55e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/84ce55e3948e3092a6ae80a0d2b2ea9a7d58bacc))
- **portable_dropbot_controller**: run self tests for the hub ([`a38d403`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a38d4037da5a007e244c29bc29611d03afef0984))
- **portable_dropbot_self_tests**: add self-test hub contract ([`496d404`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/496d40466d825bcf937e53d075dd2189c12dbc05))
- **portable_dropbot_controller**: check firmware, lease the port, decode alarms ([`ee3ddc3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ee3ddc34378c4313986969a68b068ca45b9a4285))

### Fix

- **portable**: flick-scroll panes built on first show ([`063e728`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/063e7289a9192182bf520dc4b3c4adc2d2037376))
- **device-viewer**: sample the histogram only while on screen ([`5e8a87a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5e8a87a9872ed6347b42a4bc9858450a530f0dcc))
- **camera**: keep the binding when the same camera stays selected ([`4df68b6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4df68b6e1bcbb7d111245493cd35efbb5b8afb63))
- **user-help**: start no web view until a simulation is picked ([`d0f79f4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d0f79f4f55fae45433091a6dcf6e2211201e6150))
- **dropbot-status**: give the model its preferences at creation ([`9827d98`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9827d98980348812ccb9411f1fed613a8a65e692))
- **portable**: never let a connect attempt block exit ([`97c75d1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97c75d12e038ace27edee30a0ec8341e003b56cf))
- **image_viewer**: resolve each plotted experiment folder once ([`89a5d0c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/89a5d0c946b44b094e397e9a48ed98a9f5ee6b8a))
- **portable**: set up the window and flick scrolling on late loads ([`d9717d5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d9717d5ca15bba4c8c310d9d29d777a667040e31))
- **preferences**: show the panes of plugins loaded after first open ([`5b5e08e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5b5e08ee09179ae5e6e202e5099d76e901b10771))
- **launcher**: let a deferred plugin be listed by its class name ([`b4fac38`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4fac384f4c2911a98faec6d48b8ec29da952cfa))
- **plugin_management**: keep task extensions until a window is active ([`907c50b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/907c50b14d3e9daca030ffd9169a3be6e80f3cb3))
- **camera**: show the camera properties lookup in the panel ([`0dc3fac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0dc3fac1b4554c35fd5e6744d3c52e6bc46fba18))
- **camera**: look up DirectShow controls in the background ([`2623626`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2623626b8fd97c78a3acb83bb3f892bcaa25b98c))
- **camera**: keep DirectShow calls off the GUI thread ([`559a4b3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/559a4b31eb5432f1584b775190a71d0b0548044b))
- **portable_dropbot_controller**: fast link loss ([`2a466b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2a466b85bd4925d4cc69abe8f482b6310628d435))
- **portable_dropbot_controller**: home clears FAULT ([`40e4aee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/40e4aeeffed885c191400eb29ad90dd98c41ee60))
- **portable_dropbot_status_and_controls**: motor .28 text ([`4cf815d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4cf815d5b27a6fad59cc32c2b0d3237bc3578210))
- **portable_dropbot_controller**: report refused electrodes ([`19133fb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/19133fb0ccc7eb0ecea657e842eaf635398cbdbb))
- **portable_dropbot_controller**: uint16 heater PID ([`ff56b53`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff56b5355274386c36d3b4381240615e1537b046))
- **portable_dropbot_controller**: mark stops urgent ([`586eced`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/586eced9fee4949a24d4167d38a1661e16c9950e))
- **portable_dropbot_controller**: home all on an empty table ([`643cb77`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/643cb7797a4c758ae4f988901e6ce6d99c5a9533))
- **portable_dropbot_controller**: match vendor motor params and heater ([`7532399`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/753239905492e032fe7a7fe0eda772de6825f09f))
- **portable_dropbot_controller**: use PMT presets 1-6 and the real park ([`cd6d55a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cd6d55a38050450937bcdc425aa01e6ee3113e85))
- **portable_dropbot_controller**: decode motion replies like the vendor ([`12fdd47`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/12fdd474eb059013a93e9bd4a2d295df5b19656e))

### Refactor

- **device-viewer**: share the deferred section state ([`df38819`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/df388192c4f037234d3d704f87ebe43b50979af3))
- **portable_dropbot_controller**: fitting phase in consts ([`0c708a1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0c708a189e20c481982daf6ba7d30089428cb869))
- **portable_dropbot_self_tests**: use test_title() ([`e221711`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e221711a40cd4a78074e4635cefc8c8cc27bd45c))
- **portable_dropbot_controller**: split consts into a package ([`999ad78`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/999ad7801e2c7d03bbb36d460501f2ac40cfdea6))

### Perf

- **image-viewer**: build the ROI pane on first show ([`c52b4fc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c52b4fc1edee1f9077826247ae92b940bf5fe058))
- **device-viewer**: build the Recording Viewer on first show ([`b712fad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b712fad8a591c36c56adac4ce74907aaceaa732d))
- **logger-ui**: build the Log pane on first show ([`2d2a98e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2d2a98eaf1d1f876280aad856ebf663187c0dd33))
- **image-viewer**: build ROI pane sections on paced turns ([`5fc120b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5fc120b649cfd2bba472f9273ab0ba9999a900bd))
- **image-viewer**: read plotted experiments off the GUI thread ([`f614615`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f614615dbc25bbbf3ce24731b0562859896a3a81))
- **image-viewer**: build ROI table rows only once they show ([`7a0651f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7a0651f070cef8be03706b3f4fc107d4ef3a3c71))
- **app**: pause garbage collection for the launch, then freeze ([`fb95bf6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fb95bf606d1d1e73e85efb2c4adfc83d5f2df123))
- **user-help**: read tutorial pages off the GUI thread, each once ([`de8915c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/de8915c9387585f7b075ff39019bf55ce5f2a1b4))
- **device-viewer**: pace sidebar section builds ([`eab2504`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eab2504779fcd8032dac5bcf91ab23b15419a76c))
- **plugin-management**: import deferred plugins off the GUI thread ([`434eef6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/434eef645270756675ed28a3c34ed82dc5868c40))
- **plugin-management**: mount live panes one per paced turn ([`751142e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/751142ec71246c33e5d2ff0e5431e77cfe4dd768))
- **launch**: show the splash before the plugin imports ([`1e724e0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1e724e04eb5b83835960c77a2b1badb079680cbd))
- **device-viewer**: build the sidebar after the first paint ([`c25cda2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c25cda27f7dc415af5792abb00064f9de4978f40))
- **launch**: import plotly, paramiko and pyplot at first use ([`8f506b3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8f506b3fe9530665ab3f7cf6bf731ce1df3a061f))
- **image_viewer**: import scipy and matplotlib at first use ([`ae236c2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ae236c296cfe1907092db0401377e12e0b7fb1e1))
- **launch**: defer the image viewer, user help and SSH plugins ([`d41904a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d41904a1659609def06aa758a59c1822cd90c180))

### Docs

- **plugins**: describe how late-loaded plugins are picked up ([`449d0a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/449d0a7c0ba2fb4966bd39336930c49112876d02))
- **messages**: self-test health tests and diagnostics ([`fe7e2cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fe7e2cfc81e80b609e7400ad8223eaed80e9fe30))
- **messages**: document the heater auto-tune flow ([`51d1270`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51d1270966f7f57b3d1304ada3b61c607d34015a))
- **messages**: document portable status events ([`36cc59d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/36cc59dc55a1bdf5c8afb3ca4fe600a48ad79475))
- **messages**: document the portable 1.8.0 alignment ([`2436ad4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2436ad432dbf499368c3efc3bb430875cc82b88d))
- **preferences**: chip sensor is the default chip-detect rule ([`fa672e6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fa672e632de4474b34d2892dcb92cdb5507fd8a8))
- **messages**: document the portable 1.7.0 alignment flows ([`0e2ee43`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0e2ee43ff014f3920a9439baa21587da50ca493d))

### Test

- **microdrop_utils**: fake only the update step's own sleep ([`06060e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/06060e13bc169824e7d23e2638be16e537531b1e))
- **portable**: give the listener stub the request-gate hooks ([`9b29fee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9b29feea6cb9447d7da3709ad33e2c9499df1280))

### Chore

- **image-viewer**: plot many experiments in the comparison demo ([`368d90f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/368d90f99c6497301eda75f0eceb1ab250597bcf))
- merge the self-test health tests and board diagnostics ([`0c8dacc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0c8dacc3e88561094d21fba080024bdcd84a0ada))
- merge the portable heater auto-tune ([`99b75ed`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99b75ed94b183e7f975c1e549fc98626fe7e5aff))
- merge the portable status events and heater 2 readout ([`a95e8d4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a95e8d41731e7d0a233c975f980f8a7e34f6ffba))
- merge the vendor 1.8.0 fixes of the 1.7.0 alignment ([`f7ceae8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f7ceae84b68e51e2b78fa762ac64996efc05b491))
- merge the 1.7.0 bench integration (hub + alignment glue) ([`836a406`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/836a40670adf1a7d3aec5fc028f98267eb3c75c2))
- merge self-test hub onto the 1.7.0 alignment (local bench branch) ([`4a9fdc1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4a9fdc10fb11950c3c3d80f5a7e34769c710a663))

## [v1.47.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.47.0) (2026-11-23)

### Feat

- **app_updates**: add the Updates menu and launch check ([`f9e9955`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9e9955e7e231d1a2262852ffa6d7ef4bd38bf44))
- **app_updates**: add the updates dialog ([`05e4731`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/05e47319d51bc4561164e48ee102a8b863129b00))
- **app_updates**: add updates model and messages ([`56a3c9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56a3c9b8298ae59bc15bcc066468164470a1fb7a))
- **microdrop_utils**: add per-user environment variable helper ([`012f4a4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/012f4a4c7a3f793dfe660de8fef7769f48ab05ff))
- **microdrop_utils**: update source only by policy at startup ([`208ce1e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/208ce1e9a7489ffed6d21237d8c6fd11371eeb97))
- **microdrop_utils**: add source version helpers ([`265fd05`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/265fd05446fb9406e8ddaeef672861192c001265))

### Fix

- **app_updates**: say when a switch needs a new login or backend restart ([`29697cc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/29697cc0ecf98f639c11c205dddb980c48385c5f))
- **app_updates**: always load the Updates panel with the frontend ([`91326c5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/91326c52f087a433c0bf0e51f34f517676fa3a2e))
- **app_updates**: keep the update policy in its own file ([`712d8cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/712d8cf971572a4eeabfec222288411d17899008))
- **app_updates**: keep deciding when the fetch fails ([`569e439`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/569e439fc5b5fe698906e5950369fb2b8000457a))
- **microdrop_utils**: retry the startup switch only on a lock ([`8074675`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8074675bd7ede1413bad87c00311563b22b51abb))
- **microdrop_utils**: leave detached developer checkouts alone ([`e21af20`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e21af2038f83c39a19eab87001240a6942a8eae0))
- **app_updates**: run the launch check on a thread ([`3c0e951`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3c0e951780ecacae30f4e6d4eac5db97e3b541d7))
- **app_updates**: require an explicit pick before switching ([`3864134`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/38641342c9363d49c008d28d724bde326412dbc5))
- **app_updates**: handle a refused exit and polish the dialog ([`cb47780`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cb477809a8259c1ed5850bacf00e4f63bc62d4aa))
- **app_updates**: make the updates model self-guarding ([`ca829f1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ca829f11d5bea801a9d7c16be66972a6629a27a7))
- **microdrop_utils**: honour the saved skip variable at startup ([`3c33c1c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3c33c1c053de0fe6040d42849e69d26832094ecc))
- **microdrop_utils**: harden the user environment helper ([`7b15094`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b150947b151392baff7bd9e56152c68ad6dc9df))
- **microdrop_utils**: hand signals to the restarted app ([`432b35d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/432b35d959d7a94db229353ab93944f1cc16fb2a))
- **microdrop_utils**: never raise when reading a preference ([`b888d12`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b888d129eb0e924a07f589d0188f452d6098f35c))
- **microdrop_utils**: harden source version helpers ([`51851b1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51851b1c425bb6dcfe65a3c73b71da149247c15b))

### Refactor

- **app_updates**: keep row picking in the controller ([`b57b9b3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b57b9b3665f5567e7dc966f975cdbe92cd5e7a7c))
- **user_help_plugin**: drop the Changelog menu item ([`abb9eaf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/abb9eaf9c49f4a78f9690dedadfef961940b41d6))
- **microdrop_utils**: share the application home setup ([`c54ec09`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c54ec09312f5c03f42a3bc9ed0b6f62622a86c28))

### Docs

- clarify which checkouts the update policy moves ([`c443302`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c443302f5a419cfea834eda361e886b716c6fff1))
- describe the source update policy ([`1b34851`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1b348515e0904abf349ee579d7dae5604888b8b4))

### Test

- tidy the updates tests ([`666ff7b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/666ff7b818d00270c576aeac3144cc72b804b6f0))
- **microdrop_utils**: share the git repo fixtures ([`ee348e0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ee348e0e03da9d7003bad5a2d07a6476adb0f707))

## [v1.46.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.46.0) (2026-11-18)

### Feat

- **image_viewer**: ROI tree with a section per experiment ([`5a4ae80`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5a4ae80114df36dd2faef81df48b2fa4bd38a8fe))
- **image_viewer**: plot ROIs from several experiments ([`fdc1258`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fdc1258b446aadd2f3215be87d98560f890a8576))
- **image_viewer**: copy the image with its annotations ([`6d4f13b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d4f13ba915e360c62ab0bd90096bbf26277d5ec))
- **user_help**: style the simulations contents tree ([`89c6360`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/89c6360f61a89fd0d9b294383bf4b94e0cf8dffe))
- **user_help**: contents tree for tutorial simulations ([`d245520`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d245520b68a40eec9a3aaacd8d9e246e7a39c43f))
- **user-help**: open the installed launcher from Help ([`4155a4f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4155a4f0ddfd0ccb1e399dbafa4ad338ac920b30))

### Fix

- **image_viewer**: fall back to CPU on a SAM GPU reset ([`5beeb95`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5beeb9591a34f38b243179547693e8dbfa514e54))
- **utils**: keep armed mode buttons checked ([`ec86474`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ec86474c234a01c771d861d36193f48729521e62))
- **device-viewer**: keep alignment on bundled-device copy ([`9fe72e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9fe72e180fbd8ce7e843848468bdb3b796ed7434))
- **device-viewer**: load default device from bundled file ([`7860756`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/78607569c889a79ef164919c99427dc69eeb7af3))

### Docs

- **device-viewer**: fix bundled-device rows in tutorial ([`79aed23`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/79aed230ee9a8ae54d9e8e1ad29d4a794908887b))
- **device-viewer**: describe bundled devices in tutorial ([`785dec9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/785dec9c12588360cfe08e054d7152ba4c67ae75))

### Test

- **image_viewer**: cover plotted experiments; add demo ([`483c020`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/483c020e1d4758fd686c41d995aefb0f3eed94fe))
- **tools**: unit test the file-length ratchet hook ([`cea511c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cea511c8d5583a4af7bf44e46a556438e14da675))

### Chore

- **tools**: add file-length ratchet pre-commit hook ([`f50f43a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f50f43a2e50fbff083344c90e9ae4c582be4692b))

## [v1.45.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.45.0) (2026-11-16)

### Feat

- **dropbot_controller**: skip disabled channels in scans ([`4577c0a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4577c0a66f9b7b31fea7617b7f5446ae78c92c76))
- **controllers**: refuse user-disabled channels ([`f3328da`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3328da8aef154ffa697c39356895fa014fc74e1))
- **device_viewer**: split user and hardware disables ([`2ea0dac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2ea0dacf76634e34317d98934f3490d8e672e7ad))
- **user_help_plugin**: add the Tutorial Simulations dock pane ([`04f2c15`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/04f2c15683dfe7e006c9086304362a1e1fefba27))

### Fix

- keep QtWebEngine views out of the app on Linux ([`47d4b64`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/47d4b6466a067c94f449a098dc3ae4bd2ead0003))

### Docs

- **messages**: describe user vs hardware disables ([`641329f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/641329f64445c52a015a23057ffbc629886c8e43))
- **user_help_plugin**: add an interactive run report to the tutorial ([`3c72077`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3c7207777428281cee7f50be5cfe326d72f5dfd2))
- **device_viewer**: run two routes at once in the several-routes demo ([`f6dab1b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f6dab1bc55c44fea35eb1cfc6dc2fb1eebaf823a))
- **tutorials**: name simulations whose heading is ambiguous ([`14798f8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/14798f831a69d36c5f7c13b22756b140c1de776d))

### Chore

- **dropbot_controller**: ruff-clean droplet detection ([`88eb635`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/88eb635b5c8877f0e844bd6b9e0729f95aa4a3a7))
- **mock_dropbot_controller**: ruff-clean mock_controller ([`3bf9135`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3bf91350cac8c24bbad90850cf2d4f99d54b9ed2))
- **device_viewer**: ruff-clean electrodes.py ([`5cf4e6c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5cf4e6c1187c17869cc71c314e0eb7ac0fd03f2f))

## [v1.44.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.44.0) (2026-11-16)

### Feat

- **device_viewer**: glyph buttons in the alignment presets strip ([`b4947c0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4947c09b404fc6fa1b2b3d61393c28959a44873))
- **device_viewer**: show camera and scope in the presets strip ([`c3cc575`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c3cc5752722b87e1647d47c8b16a95fc095de3f8))
- **device_viewer**: remember the alignment per camera ([`93cbe35`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/93cbe3510115af687da09d95a1cf809c5dbbf705))
- **device_viewer**: presets table follows the camera ([`6e1338d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6e1338d8f78b9fdfe16ec13788826e36faf5367c))
- **device_viewer**: presets schema 2 with camera scopes ([`aac584b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aac584bb083907593e5b4c317ff008d7c532c205))
- **device_viewer**: camera identity and preset scopes ([`623639c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/623639cf10db23477cdc1564112c06456383d7b0))
- **portable**: chip engage mode preference and alerts ([`cab4504`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cab4504dd540c9ff2cb7599b80c1da26ba7ca34f))
- **portable**: smart chip engage in the backend ([`34d3899`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/34d38998d3920b57cb5095b005fe4684aead001a))
- **demos**: add a Touch mode demo ([`dd28ff4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dd28ff4315c953cd6428b1477ea7a5c6ebdb7688))
- **portable**: describe the portable controls ([`9c0a39a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9c0a39af67a664724372eb89dbec76b46dc12f25))
- **portable**: show Portable DropBot Settings second ([`04b5478`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/04b54780c6c2eb335635bec5fc307664fe90f379))
- **touch**: scroll tab bars by drag, with larger arrows ([`c188fb4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c188fb44775daff0c064edd8d5a17f2a4e806381))
- **protocol-tree**: add touch Select mode and a menu button ([`e9eb4b9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e9eb4b9e5cc108201b2492bffc5f469bddee5e06))
- **touch**: add Help mode to read controls by touch ([`f515d3c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f515d3c697bc42bec4fdf023bdde08a33b9d95e3))
- **touch**: add Touch mode with steppers and a number pad ([`f7ae6b4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f7ae6b45f3935d03e00306109388c59d3c30fc00))
- **examples**: pick a Tutorials menu section when scaffolding ([`f5abd91`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f5abd911022a88b00fe2c43706c2aeabf78dde66))
- **user_help_plugin**: order the Tutorials menu by learning path ([`19bce66`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/19bce66b6ede53970ab38791b003fd3e3abba119))
- **device_viewer**: overlay device on aligned video ([`bcdd1b1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bcdd1b16227448f32e01cdaeb9a4ab7e97970275))
- **device_viewer**: record overlay sidecar with video ([`2d9d3ce`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2d9d3ce074e9484b655d8290a8e84a5a9412c187))
- **protocol-tree**: drag selected rows to move them ([`0bcfc49`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0bcfc491755a3f1d9f1390713f72df94323bcc85))
- **protocol-tree**: add RowManager.move_rows block move ([`76e3572`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/76e3572a675a48d4bd59aa89f76e9cd8f03ecb28))
- **device_viewer**: list the Device Viewer tutorial under Help ([`1885a5a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1885a5a20cd98d28e40a7f04237580126f07c67b))
- **portable**: find droplets with the driver's finder ([`2ed771d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2ed771d958eedde4522a7fedcc634f79cdb97d3c))
- **protocol-tree**: AutoSave checkbox on the navigation bar ([`b84bd2a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b84bd2adf406a7693e1842792195cc45669ceec7))
- **quick-actions**: add Undo and Redo toolbar buttons ([`3c56aea`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3c56aea271383b863870fd2bff95868e847a8e3c))
- **protocol-tree**: let quick actions refresh their tooltips ([`c54da70`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c54da70806d38da34c6acd6c915ae6641c4815d4))
- **protocol-tree**: undo/redo protocol edits from the pane ([`2959645`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2959645fde1a602e277c55e7040cd347158103a0))
- **protocol-tree**: record protocol edits in an undo history ([`e53b7f3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e53b7f3f140aa0d555af4bc58d8d30b394886525))
- **device_viewer**: make Commit to Step a tri-state button ([`1288104`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1288104c5d812d7479edeb56c7bfd01e9c9744c4))
- **device_viewer**: auto-commit sidebar settings to the step ([`cfedb30`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cfedb306aa142538651fc6e3d7fe6eebdc7e53a6))
- **protocol-tree**: AutoSave glyph in the status bar, on by default ([`d84da33`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d84da3317875c60e39dbc68ccf6160115fb51ad9))
- **style**: add the save_clock glyph constant ([`297f77b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/297f77b49412b30edc09f06ccaa97875a20ae0b0))
- **protocol-tree**: AutoSave toggle on the quick-actions toolbar ([`523f45f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/523f45ffbd3e04343e98c81c3a1159b94e106fdb))
- **protocol-tree**: add the AutoSave decision model ([`96fd4c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/96fd4c1eaa8c3722c516681f6d83d7e56d851ce1))
- **zone_protocol_controls**: zone target protocol column ([`52cf156`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/52cf156ce018876a53f533a91b249a5ac1621668))
- **pluggable_protocol_tree**: let columns add step electrodes ([`fb2d163`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fb2d163842620e730ff7f1e2114e03dea87573d9))
- **device_viewer**: rescale saved camera quads to the live frame ([`0c5601e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0c5601ece42b529b19d7a65f9ec6f5a50326cff8))
- **device_viewer**: save and apply camera-alignment presets ([`6bfc291`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6bfc2914fc1cd26e6f7aabf8a6ec94563d229e61))
- **device_viewer**: presets strip in the Camera Alignment window ([`839e7ba`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/839e7bafc1d478dfde4ceab4f5c1d57744a52fe9))
- **device_viewer**: presets table and naming models ([`4957539`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4957539f741f67fe0e75f290c7c5c83c1dd747ba))
- **device_viewer**: store named camera-alignment presets ([`f7c5f72`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f7c5f72d289260dc34bb81a443991d004b83f16e))

### Fix

- **device_viewer**: clear the undo stack on a camera switch ([`2872a6d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2872a6df88e11c5e3addeace9488e281caf9c72b))
- **device_viewer**: check the V4L2 node pairing before using its id ([`b8bcea4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b8bcea4dab790c1a364446b2b145ff72b274646d))
- **device_viewer**: Scope picker binds to the loaded device ([`dfef612`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dfef6124e27dc0f50d7ba0566f64f0ee6f579734))
- **device_viewer**: carry any-device presets by scene rects ([`bedea06`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bedea06fdcc490d315ca57b8a30362c7177dc4ae))
- **device_viewer**: keep label-only last-used records shared ([`f803403`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f803403be6ba3fef6358ad34b047e7d53a5147a8))
- **device_viewer**: start-up hand-over waits for a camera ([`178b147`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/178b147f7f0ac1f5c0788b8f91c938e62ed18f55))
- **device_viewer**: restore skips defaults it cannot place ([`51a0720`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51a0720a09e87c776a68159753392d2f2661eb22))
- **device_viewer**: keep alignment restores off the undo stack ([`395d2ca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/395d2cac092f04f144b35c4d49d590c40971f469))
- **device_viewer**: stop a running glide on a setup switch ([`5097e06`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5097e068a7892e528d4ac381a7b68865fc88708e))
- **device_viewer**: only Reset forgets a camera's alignment ([`486c71a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/486c71a44d04db5a9f55814f9844f094bd919621))
- **device_viewer**: Apply keeps a working alignment again ([`f3bf021`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3bf02152a22043ad85851c51aa25d17a1f031a6))
- **examples**: keep an SVG's own title in its drawing ([`30e01a8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/30e01a854d23ba131e69fa5ccdb32f7488917baf))
- **utils**: keep preset buttons from being squeezed ([`9a99b2b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a99b2bd3e98d7ac9bd0991766927b267df7f16f))
- **utils**: apply item tooltips in custom TraitsUI editors ([`ba0db23`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ba0db23749a5d8b7b7419fcd0f03133db360926c))
- **protocol-tree**: AutoSave checkbox beside Phase navigation ([`a254871`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a25487195e37cfd7889f71e52e7b68ada4756f39))
- **portable**: stop rescaling driver status values ([`2cc289d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2cc289d38ad3f0ef52ee442c484686b9a5cbdc40))
- **portable**: drop removed driver commands module ([`71e365e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/71e365e66961bf6adc76995b7c84e5fe369aaf41))
- **device_viewer**: enable Commit to Step for every setting ([`904ef9a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/904ef9a127f2daf216982366012d51a507ae332a))
- **device_viewer**: stop replaced service redrawing zones ([`b23fd53`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b23fd534a127b661db6e581c72033a3bcb57f25c))
- **device_viewer**: make applying and saving presets lossless ([`83c7f4d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/83c7f4de05b1acd08241edf21373bedacec3f609))
- **device_viewer**: truthful endpoint Reset prompt with a default preset ([`b6f35a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b6f35a7bc3ef17312790e3b92a17a84f2be894c8))
- **device_viewer**: say when presets are read-only or cannot fully apply ([`dcd5bc9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dcd5bc90facbd96ba3628b087045aa129affd7df))
- **device_viewer**: keep presets files the store cannot handle ([`536e4c9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/536e4c99df648fd279c6502b9644fcf8b52bb789))
- **device_viewer**: never write over an unreadable endpoint cache ([`3740da4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3740da4ae95478c81f0a333160507192433888b6))
- **microdrop_utils**: harden the atomic file write ([`9865556`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9865556cef9f8453d5addd9a306e58730d3835ee))
- **device_viewer**: keep the presets highlight on the selected row ([`9eea7af`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9eea7af85705e6590d188af744fb2983e5d85011))

### Refactor

- **style**: share the stylesheet block helper ([`caf0d82`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/caf0d829082bd4fe0ac8a080b8128e1a3c16229e))
- **portable**: return the error from _proxy_call ([`06d4990`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/06d4990ecf145c87138452b06bc7fd6a364ad417))
- **device_viewer**: pure camera-to-item alignment geometry ([`8e7a18a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8e7a18a9533b41259286c3523cc9d5677eeae164))
- **microdrop_utils**: share the atomic file write ([`ea7a144`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ea7a144b2bf23cde0aa029a85e92c66dd25b6514))

### Docs

- **image_viewer**: list the Image Viewer tutorial before analysis ([`2755e76`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2755e76fd327cfd46600360dd06830654d81ce3b))
- **image_viewer**: add the Image Viewer tutorial page ([`3b5c104`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3b5c104f1690563eb46b10996057a901a0d55dd9))
- **microdrop_application**: let long defaults wrap in the finder ([`17a4783`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/17a4783ba648bf768006ec6ed13fcff69022914b))
- **microdrop_application**: add the Preferences tutorial ([`40e95a9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/40e95a988e8ee059257f61174b7e827412006b06))
- **pluggable_protocol_tree**: list the Protocol Files tutorial in Help ([`eaa31f3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eaa31f34a0a598211384fe9eeea3d3756033e586))
- **pluggable_protocol_tree**: add Protocol Files & Experiments tutorial ([`4e17096`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e1709644f408d3f96590060c25cf3dfd71d5901))
- **device_viewer**: real footage in the Recording Viewer tutorial ([`a34b563`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a34b5635c034fc98695b425e02eab5c01fc26e27))
- **examples**: list the Recording Viewer in the Device section ([`f01d20a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f01d20ad99fb29afcf07a7210ca19723c0ea6a1f))
- **device_viewer**: add the Recording Viewer tutorial ([`68fb906`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/68fb9069616aaee7ce261b66674be95ab4cdd946))
- **image_viewer**: correct the analysis guide where the app moved on ([`0307482`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0307482c131cec8adbf3798493f5a52a99f34487))
- **examples**: point the shape-series generator at the kit source ([`4ea91f4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4ea91f47d9dae1982fbcbd00d4e7a16a369443bc))
- **image_viewer**: build the analysis guide with the tutorial kit ([`2a6b0fb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2a6b0fb957731bc83e483f4b703f6984f81b85ed))
- **image_viewer**: compact the guide's example plots ([`39e244c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/39e244c9ddef5d457db20bf39c85cfd16a6b4e98))
- **device_viewer**: list the device files tutorial in Help > Tutorials ([`90ed6aa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/90ed6aa1a4cd03be10bd26f3abfd11f9f76b0e14))
- **device_viewer**: add device files, channels and connections tutorial ([`a1096b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a1096b8b00539da87625bb06ec90a5d1dc8cfa8f))
- **ssh_controls_ui**: list the tutorial in Help > Tutorials ([`1fba3c5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1fba3c57983d1fe411fcb19c914dd32e0bf602b0))
- **ssh_controls_ui**: add SSH & remote backend tutorial page ([`412ff7f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/412ff7f9343faeda301e2c1f29886eed47994c2a))
- **dropbot_status_and_controls**: finish the status tutorial ([`a864a4b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a864a4b9580f90e9f41c36abd32e022bd7805feb))
- **dropbot_status_and_controls**: add status pane clips ([`ccfb335`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ccfb335f98330d626b645b6b5f727c97502bf1ca))
- **user_help_plugin**: say Tutorials are listed in reading order ([`f2ca6c7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f2ca6c707077349219acf2abcab3cefd95ac0e73))
- **device_viewer**: drop the simulated-footage caption text ([`c8a41ae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c8a41ae95de260152e7402a690576f9cba43f6bb))
- **device_viewer**: simulated No Droplet run for Zones ([`4303ba2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4303ba2016f54276748963a3d41592bd5dc20e1b))
- **device_viewer**: simulated clips for the Zones tutorial ([`db9874a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/db9874a68a95f1bfcdfe0ab8290cb4b2d7c94420))
- **device_viewer**: drop the simulated-footage caption text ([`ceab1dc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ceab1dce58d376d32fd7c5be726a56f81f0bf86b))
- **device_viewer**: simulated Lin Reps and mode-label clips ([`4cf2beb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4cf2beb108fbf8953470b09459637ac5588d4828))
- **device_viewer**: simulated clips for the Device Viewer tutorial ([`014458b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/014458bef760b19f84e1164b468f1ed6f55c932b))
- **tutorials**: let a clip keep its poster as a sidecar file ([`56fce96`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56fce96563012512f608f92e153dbc6233548c43))
- **pluggable_protocol_tree**: drop the simulated-footage caption text ([`4c7c489`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4c7c489175d9be6e392c60aaf0bbc59d485d6618))
- **pluggable_protocol_tree**: simulated clips for the Protocol Tree tutorial ([`c460d70`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c460d70f0ea6fc78f66cb57df762dbb50e13b38b))
- **user_help_plugin**: list the help and logs tutorial ([`4f9bb9a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f9bb9aadf2dfcd82ad320ac384a7ece3bea4e0c))
- **user_help_plugin**: help, logs and saved files tutorial page ([`3365042`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/336504260d952be3f6783df5fcc3f5f9681fa8be))
- **microdrop_application**: add shortcuts and touch assist tutorial ([`bbd593f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bbd593f02a3853b7ed54367ddd016aaf5336ae61))
- **device_viewer**: Zones tutorial ([`3615754`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3615754bfe37842865af3ebb43a4659de292e1d8))
- **device_viewer**: add Zones tutorial clips ([`6a9d51b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6a9d51b2d962f090935a5032200320e8b5963fdc))
- **device_viewer**: show the Unsaved Free Mode Changes prompt ([`936c31a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/936c31a2acf0e6ea85e7859315aaa8a488cebdc3))
- **device_viewer**: add real footage to the Device Viewer tutorial ([`f03aaf1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f03aaf1c04576ab736b97567c8ca252dcd7e3115))
- **device_viewer**: add the Device Viewer tutorial ([`23ee5c0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/23ee5c08d852940c1cd0c60b78cd0b1c9712d94c))
- **pluggable_protocol_tree**: real clips from the new user takes ([`a005dff`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a005dffb0dae56ad98b92c6a0a944c1e01272337))
- **user_help_plugin**: real clips from the new user takes ([`91fce1a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/91fce1a457a61f3dbae82cf3be6873eeba357e4c))
- **plugin_management**: list the tutorial under Help > Tutorials ([`e7d8853`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e7d8853ed7903101e563861695be5d575bb4e02e))
- **plugin_management**: add the plugin management tutorial ([`ef63d41`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ef63d41bcf765b0175dce91e7bba2beb29ac169c))
- **protocol-tree**: document undo and redo in the tree guide ([`f6c1e03`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f6c1e0381c5caffe3a2732c4611273892a072b29))
- document the zone target column flow ([`bb9289c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bb9289cb77a5bd29eb64dea908a962eb59d45135))
- **examples**: presets strip in the camera alignment demo ([`9a35b03`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a35b03e9e6f3f341631544d0ce27459e16d71d5))

### Test

- **examples**: check the Preferences tutorial against the code ([`f2676f7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f2676f7c01b259e652c242a87f6839a67c423158))
- **examples**: expect the Recording Viewer tutorial ([`19eae4b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/19eae4b8bb58ad738c7019b3c3ae20b39e522770))
- **examples**: check the image analysis tutorial rebuilds identically ([`a4a6633`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a4a663386bb14d638c73d035e13d3e021e72268e))
- **device_viewer**: check the device files tutorial's arithmetic ([`65882a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/65882a23874942e6cf66b9db5cd07e7eb6897d53))
- **examples**: cover the SSH & remote backend tutorial ([`fce4059`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fce4059cb341a0581a7fe9cef64c53ed1d28a9b5))
- **examples**: read the standalone build as UTF-8 ([`bd0821e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bd0821e29990871147d343f8bd35b1546270b938))
- **user_help_plugin**: cover the help and logs tutorial ([`5dbfa2c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5dbfa2c91b73d2c5ba151e35a967ddcae2b2a155))
- **microdrop_application**: keep the shortcut finder in step with code ([`18649db`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/18649db326eb5e3ec01509137a051ade318cb1a0))
- **device_viewer**: cover the Zones tutorial ([`a3733ae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3733ae2a32fc079534f2815f47bf9cbeec6c3ce))
- **examples**: cover the Device Viewer tutorial ([`a0f29e9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a0f29e9edf1596a9fd99e1504d5fb4d1fc47b84f))
- **examples**: cover the plugin management tutorial ([`d3b8af9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d3b8af968e687fe49d926385dd47af1a3312beb5))
- **protocol-tree**: undo after an AutoSave is saved again ([`97ae4a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97ae4a2374bf0b2e836d5639c335b2c20c166d6e))
- **protocol-tree**: cover the protocol edit history ([`c71ac0d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c71ac0da86501881ae486808be5e309b169d75c2))
- **device_viewer**: cover camera-alignment presets ([`e7a50a6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e7a50a6395391015e667c176d928b61dc13dd91f))

### Style

- **portable**: ruff-format calibration and advanced views ([`7bdc94c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7bdc94c6f3b0edbdc59bf7663fdf382fe753edc7))
- **protocol-tree**: bring navigation_bar.py ruff-clean ([`b260106`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b2601060f9403c22f25f8c4adc6056a80c9744df))

### Chore

- **examples**: retire the analysis guide's own glyph tracer ([`c1349c4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1349c4d62f9b56e63909a8301b00f6d7b40fa43))

## [v1.43.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.43.0) (2026-11-12)

### Feat

- **help**: device viewer contributes the Camera & Alignment tutorial ([`20688c6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/20688c6ef1cee7eb1f55c604ab520ecb8bb0250c))
- **examples**: linked sidecar documents and a single-file build ([`1fcc269`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1fcc2692d7a416e658e2e31d98bb5543cc7ad35d))
- **examples**: ship tutorial clips and stills as sidecar media ([`4f27cf0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f27cf02ea2e79cb395a76e924c2701e4e4dfcb7))
- **microdrop_style**: chip player and clips in the tutorial kit ([`1b64716`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1b647166c0027700b428e35f9d58d16daeb361a8))
- **help**: image viewer and dropbot plugins contribute their tutorials ([`a45e981`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a45e9812b3406b02be300c8e8b3783ac2c609889))
- **help**: Tutorials submenu ([`b13f9a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b13f9a735fab0f75b16dc768b13ae84bcc91f63b))
- **examples**: tutorial build and scaffold scripts ([`50f6c08`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/50f6c087cc16ab93fd83af284000b50f3175b213))
- **style**: shared tutorial kit (css, js, glyph tracer) ([`2b23998`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2b23998ae3bfa20041ec0af7ed20c03c63aebedc))

### Fix

- **microdrop_style**: open an inlined document within the click ([`7bb44d3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7bb44d32cda03cf99d88bd3d730e21e33396cd58))
- **examples**: refuse a network href on a sidecar document link ([`2e97c07`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e97c07f572e31fec6f4b8f28e008d8bb2253869))
- match sidecar documents in any folder in .gitattributes ([`5804a75`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5804a75a138c706120b7a6997917bd4e5395a158))
- **microdrop_style**: let sidecar links open from the Help viewer ([`7dfddc8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7dfddc82d9b866e4a43a20f7e5daf3dac18bc5ef))
- **examples**: escape the scaffolded tutorial title ([`4ab1e84`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4ab1e84a0d83514fefeca8ff7ce9fae0119a60c8))
- **examples**: fail tutorial builds over the size budget ([`c0973e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c0973e8621f67a8a28b62efb128329e9f43c0a56))
- **examples**: tutorial build errors, Qt-free --check ([`4b7a9a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4b7a9a7bfa42d885972ea505520d83646599e5fe))
- **examples**: keep style attributes, reject script src ([`c5ac51b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c5ac51b2bf668432b6afea864deafbc3a5eb8d0c))
- **examples**: inline SVG figures without alt, one class ([`688fdc3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/688fdc3f69189364669fc931f58ad3a8ee69b27d))
- **examples**: parse pages for network references ([`3a20cc3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3a20cc3a4b329f92381731840fd4ba5d356f6846))
- **examples**: refuse plugin shapes the scaffolder can't edit ([`e29ecd7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e29ecd78e1c3ee3ff31e22eb9f48debc968edefa))
- **examples**: comma before a scaffolded second tutorial ([`a636559`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a6365594241d964b2c936f8767286a6b0b985e0e))

### Refactor

- **examples**: chunk dense tutorial-kit bodies ([`29bae24`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/29bae241b988355946c4d0e72c571e278fc8738d))
- **examples**: scaffold tutorials as plugin contributions ([`0b7d4c6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0b7d4c6f53076990ed0ad9976e3a1bcaff6320c4))
- **help**: tutorials as an extension point ([`7cb97b1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7cb97b13ad302e92ff80cf6e8cd25236094a220d))
- **examples**: keep the glyph cache in the built page ([`dcd21c8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dcd21c8b263f95fa84e2401d6cb285a269f68ef5))

### Docs

- **device_viewer**: Camera & Alignment tutorial ([`f43be07`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f43be07282b90affa1f0ef1590005165af400201))
- **pluggable_protocol_tree**: list the tutorial under Help ([`c2a49e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c2a49e17618c64c52f203699c83d01154b1b8122))
- **pluggable_protocol_tree**: Protocol Tree tutorial page ([`33805aa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/33805aa2928af4e2de7427fb6456bbbf4770dd82))
- **user_help_plugin**: short looping clips of the real app ([`2c0d998`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2c0d9989a028497fb72c60e2c20255dc8491fa9a))
- **user_help_plugin**: end the run clip at its summary and ship the report ([`124c09f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/124c09f138aa6eb1718b6eedd6ecd430c13f04ad))
- **user_help_plugin**: shorten the split clip's caption ([`08dffc5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/08dffc53d482cdd6e9580ec228a40ee1a4e11703))
- **user_help_plugin**: name the default protocol folder exactly ([`e5a48aa`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e5a48aa2f1e43d56c7ad699e1cdd0b00877f9689))
- **user_help_plugin**: Getting Started tutorial ([`932a7cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/932a7cfbe96e0b97a4d66808ebd25a9629d37608))
- **dropbot_status_and_controls**: rebuild tutorial on the new kit ([`5718ac8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5718ac810f7c94ec29c470cfd8636080d5c74a4d))
- **examples**: state the offline rule the build now checks ([`aa50abd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aa50abdf416e024110d5ce62c7c822dbd12401dc))
- **examples**: tutorials via the TUTORIALS extension point ([`6e04683`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6e04683eba3dc0d766254e263be5678daef3e5ba))
- **examples**: tutorial authoring guide ([`7e0c0ee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7e0c0eeb08b94f236ab8aca2e864a84f66f8302c))
- **dropbot-status**: Dropbot Status & Controls tutorial ([`fc10241`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fc102412fd97f91cb1f9735f9eb883b78c3f8e07))

### Test

- **tutorials**: cover the Camera & Alignment tutorial ([`6d39cca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d39cca854a3f923d469e590065600659085f1a1))
- **examples**: pin the Protocol Tree tutorial ([`a63c404`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a63c404bc9347ccdb3683d1708516cbcba8781bb))
- **user_help_plugin**: count the Help plugin's own tutorial ([`237768f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/237768f0e3434e0620bac5cb7c81e51334a9fd19))
- **examples**: set the Qt platform before any import ([`9ce4181`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9ce4181f1bcdc529955b9c1789db97356e9a54d2))
- **examples**: tutorial kit ([`988479e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/988479e825fa7c4d2b741af380bd4233755c9081))

### Chore

- keep tutorial sidecar documents byte for byte ([`bb7de89`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bb7de8997485df60f2c36b1774d7114ec4544fdc))

## [v1.42.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.42.0) (2026-11-10)

### Feat

- **video_protocol_controls**: store capture camera settings per step ([`b52f2ec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b52f2ecd73f663b2c39a07efa76002934c45ff58))
- **device_viewer**: publish and apply camera capture settings ([`c7f3fb2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c7f3fb2517f43bad38bc46d7994e74c37371a255))
- **device_viewer**: actuate sidebar route runs with a step selected ([`026375f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/026375f5fe9acac153fa56d16a181ade495b7948))
- **device_viewer**: add rotate and lock to the alignment endpoint pane ([`6ef64f7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6ef64f7c37ad7082a3ca893599c028f021516f4c))
- **camera**: warn once when a resolution above Full HD is picked ([`5f71654`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5f71654c6ec79bacb8778ad4ce53631f81c6110e))
- **camera**: condense the resolution list to named common sizes ([`650f6e4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/650f6e448addc71b53bd16a9905b2e2356dc4493))
- **camera**: sensor-mode frame rates for libcamera cameras ([`5753614`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/57536145d21d9964b416be2f1af8a8e99c464e10))
- **camera**: hold the control restart while recording ([`7b2d042`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b2d04208a37ffd28879b19509aa03159eecce9b))
- **camera**: restart the Pi camera on an image-control change ([`e00e000`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e00e00074ec741619aab6336a4f758a308e24ec3))
- **camera**: libcamera image controls for the Pi camera ([`217f95a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/217f95a318a51290c7f0ed680a45203b640526cc))
- **camera**: reach Qt's libcamerasrc element from Python ([`96cb354`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/96cb354656dc03df91e41a016662d4f1367ccfe9))
- **portable**: detect droplets with an absolute threshold ([`b1fcb6f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b1fcb6f0af581ddc8f326cecc8784ba31666c6d5))
- **touch-assist**: add virtual D-pad for arrow shortcuts ([`80b2b1c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/80b2b1c03641e9188cfdda57dc5aa50a1bdc091f))
- **camera**: lift the recording cap in Advanced Mode ([`3e1e89b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3e1e89b55fa33839235275147873f91bf9d89b12))
- **camera**: warn once when a recording is capped at full HD ([`d9d88b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d9d88b0db09cd989eea421db0168a8658482bfa2))
- **camera**: cap video recordings at full HD ([`9ff31c4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9ff31c43c8fd27968de8fad4a6dcec0cfea03f54))

### Fix

- **camera**: read the selected size from the camera model on list switch ([`78f4271`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/78f427120693b56ed8bd09245029651486611c14))
- **camera**: keep the resolution notice out of start-up ([`1d65b87`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1d65b8771350801b2dc7fb165418f0d89848ba08))
- **camera**: always open on the condensed resolution list ([`f59645e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f59645efd5844442aa911ae6a9beb1426f48db9b))
- **camera**: stamp raw recordings with wall-clock time ([`e563482`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e5634822209b4a71144e659dd7076e96103d71e2))
- **camera**: record with the Pi camera's real frame rate ([`f3e5e4c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3e5e4ce911315636d7bfe8745c156c52a3e6882))
- **camera**: attach the element hook only around camera creation ([`64bbf12`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/64bbf1208d48b3e402588b3c0d9ddb419d8d7fee))
- **camera**: resolve GLib from the GStreamer the app loaded ([`605d17d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/605d17d45358f40f5e23735989532fdc37acafdd))
- **camera**: release the last preview frame before a libcamera rebuild ([`16709f8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/16709f876ebce2ce7a2f8ee82dea574f2aab37d0))
- **camera**: let a stopped libcamera stream drain before rebuilding ([`97bdf4f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97bdf4f948597d8f0ea3181b79acf8d7cc2389f5))
- **camera**: drop placeholder sizes from the resolution list ([`bafe81e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bafe81e21894b7e5c951d6da93ea1a8638a89822))
- **camera**: apply a held libcamera format 2 s after start ([`ce8da88`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ce8da88e52e080507b7380525db835487a62f16a))
- **camera**: change libcamera format only while streaming ([`509436c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/509436cd2048ce3746279df715e6f059f16b92d9))
- **camera**: never restart a stopped libcamera QCamera ([`d00a5bc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d00a5bceff9e3f61d02b3f23bb29a1aed94d5bfd))

### Docs

- **messages**: document per-step capture camera settings flow ([`03d4b3a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/03d4b3a179d0c645aadc8fa74a0e0ef5e9b0585d))

### Test

- **video_protocol_controls**: expect the camera settings field on save ([`7e9dfd4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7e9dfd44839348d569d436aff66366252c270fe0))

### Chore

- **camera**: bring camera preferences ruff-clean ([`5c5bc53`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5c5bc53554be9db8844e9256566caf812137154a))

### Revert

- **camera**: drop the full-HD recording cap and its notice ([`eea73f6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eea73f68fad4cbcc5e396ec114a1eacdfa58abb7))

## [v1.41.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.41.0) (2026-11-06)

### Feat

- **portable_dropbot_status**: droplet readouts in the status pane ([`b67f00f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b67f00f3799ed57b9ec63bcb170ac6c0d8137b38))
- **portable_dropbot**: publish chip capacitance readings ([`80f7768`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/80f776882f366ef9fe0adce127cf93264fb2c191))
- **portable_dropbot_status**: droplet baseline calibrate row ([`f9d4977`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9d49777876fc02f2f3b813e48d6c1f1108672ab))
- **portable_dropbot_controller**: droplet detection ([`b6bda13`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b6bda133b559abe59bc85ba4f1630ed2b95dacc6))

### Refactor

- **status**: share the droplet readouts between panes ([`93f455b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/93f455b1cca70960f5b34952f80e46d58d40be6f))
- **electrode_controller**: re-export the channels request schema ([`00a829a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/00a829a63d1b83a598b49f9e6fcc36773872e6ee))

### Docs

- **messages**: droplet readouts on the portable ([`2eea6ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2eea6efb53c757799f20d6f7d886c48965b748d3))

## [v1.40.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.40.0) (2026-11-06)

### Feat

- **dropbot_status**: droplet readouts in the status pane ([`e78d3bd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e78d3bda406ef34836c7d6e1aa06a41da634edd1))
- **microdrop_utils**: live tooltip and centring for HtmlLabelEditor ([`8b65fe1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8b65fe1ab3d12d8fe059ccf8d68a5f2055e89d85))
- **device_viewer**: publish a live droplet volume estimate ([`41bfbad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/41bfbadc189f2ce3db67644e85e1310f9a855c81))

### Fix

- **portable_dropbot_controller**: report the real connect error ([`aa1d0bc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aa1d0bc51685ef9ee5d3471cc063decbef350eb1))
- **portable_dropbot_controller**: drop the session subclass ([`70e745c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/70e745c5a94399ff94a7d0c6dfbf5d46340b2fdd))

### Chore

- **dropbot_status**: ruff-clean view and message handler ([`e0026c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e0026c13d704e43248c8681a04b0c5dbfe0d7e17))

## [v1.39.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.39.0) (2026-11-05)

### Feat

- **camera**: Camera Properties popout window ([`e9372cc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e9372cc0f02ba12d33aa6d19a06ae81decef7650))
- **camera**: Windows focus and image controls ([`46fe4c4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/46fe4c43cb536377bd534965e806ce4d9c18600f))
- **camera**: DirectShow and v4l2 camera controls ([`05f22e5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/05f22e59930e164fa29c3b6650deb2f62e17093b))
- **camera**: collapsible Camera Properties for focus ([`c2c79ae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c2c79aedd1a9e8ed7e84ef9b2acd4a625f4b31dd))
- **camera**: lens-mapped focus, live drag, autofocus ([`b866e05`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b866e05e645f06e5bcf60d946e61fba34c6aa60c))
- **camera**: focus row with Pi CSI lens control ([`171d25e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/171d25ed89723c986394761005bff12616561ba1))

### Fix

- **camera**: stop clipping the Autofocus button ([`cfde633`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cfde633c51326b9c8de2dee5a82bcbb12d1b198e))
- **camera**: style Autofocus like the sidebar buttons ([`ed8cb63`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ed8cb63cb841687a3ceb77aaf56f153eec7b3546))
- **camera**: disable libcamera AF so lens writes stick ([`3b11c61`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3b11c61a17b287efe2a667363cbc217098b2f9a6))
- **camera**: NV12 for libcamera, never YV12 on a Pi ([`983566a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/983566a26176e9dd0346b1974156642ea3c01a1b))
- **camera**: hide Pi ISP nodes, pair libcamera cams ([`32201cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32201cba19cf10231e9e2d00b7732f31a6f186d1))

### Test

- **camera**: give select_source fixture a stub camera ([`266275a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/266275a1516890ccaba1ea164e69303f70698f2a))

## [v1.38.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.38.0) (2026-11-04)

### Feat

- **layout_presets**: pick the preset Reset Layout restores ([`61cb697`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/61cb6973756c177ab798b42ffc9b9e7430b395c2))
- **logger_ui**: search filter for console logs ([`32d2cf8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32d2cf8df4009edf144c172354ebfbaba7ea1c69))

### Fix

- **layout_presets**: keep the window on screen on apply ([`5b61839`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5b61839056e6682615bd8ab5c5fd8874969582ff))

### Style

- **logger_ui**: bring console log pane ruff-clean ([`554afee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/554afeec806fce6be31753df540dfb7b22fcae75))

## [v1.37.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.37.0) (2026-11-03)

### Feat

- **portable**: magnet engage position preference ([`8de21a3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8de21a32ce6ca719eca22a34ca9db43478bd7330))
- **portable**: magnet engage height read/write/preset ([`48356c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/48356c1640df6fb50bd824fa46be86b80ded4efb))

### Test

- **portable**: magnet engage replies on the prefs tab ([`1987842`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1987842155a840105b57199ff561cbf007023b7d))
- **portable**: cover magnet engage read/write/preset ([`c1f76a1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1f76a12c5da4b663211a5a6b4bf5c256516dbb1))

## [v1.36.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.36.0) (2026-11-03)

### Feat

- **protocol-tree**: notice for skipped column hooks ([`d553c1b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d553c1bbf3092e5420f0608e574aac39bad26ff6))
- **protocol-tree**: bulk column-usage helpers ([`669224a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/669224ab5018bc2bdcea5c17446e157397e9d095))
- **portable_dropbot_status_and_controls**: gain, temperature and move presets ([`75cf55c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/75cf55cf9858845e729df7eb41f3e80e0ae815ae))
- **microdrop_utils**: preset buttons editor ([`e8bba9c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8bba9cd6f9cd362b66923b6f4dbbb324567f834))

### Fix

- **protocol_tree**: list skipped columns as bullets ([`fa80b88`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fa80b8828c44d1ced2ae12846ae530217c69b7a3))
- **executor**: skip run-level hooks of unused columns ([`f5a7124`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f5a7124aacd051c5e44333a506ad314e242532c9))
- **style**: resync TraitsUI field colours on palette swap ([`8c57905`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8c5790547a952c05cb87bd1198ee3776ffab06a6))

### Test

- **portable_dropbot_status_and_controls**: presets ([`21eecf5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/21eecf57aabf07583bf474a9acb0cf582df71555))
- **style**: cover TraitsUI field colours on fallback ([`e1ac36e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e1ac36ed3057f899bd4ee59e21186876a99c527c))

## [v1.35.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.35.0) (2026-11-02)

### Feat

- **image_viewer**: RGB channel mode for the ROI histogram ([`730956a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/730956ac71641503ddf0f66ed7e34f6e8590f21a))
- **plugin_management**: battery icon as a managed group ([`bc3b66f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc3b66fdee1461fea7d966b23a3add4bafd009c3))
- **device_viewer**: live region picker for the histogram ([`b968a91`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b968a915754335a009a8bc8ea08a1c13a6cd00f9))
- **device_viewer**: live histogram region of interest ([`8f9965e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8f9965e0a4417de129245f76677f947ed52b9c6b))
- **device_viewer**: live histogram region picker ([`f94ef03`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f94ef0332f617071a1885c0ea5f599d77f710d71))
- **microdrop_utils**: checked look for IconButtonEditor ([`5381689`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/538168954feb564f19c52fbd01c82ab56bf68c35))

### Fix

- **microdrop_style**: dark fallback palette when following a dark OS ([`f8eb22e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f8eb22eb335ed41d3de26f29be2911df8201ba2e))
- **microdrop_style**: verify the palette before trusting the scheme ([`9d091c3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9d091c33cd2d793fd7d760525941ab80a2f01e06))

### Docs

- **image_viewer**: histogram channel mode ([`85dc383`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/85dc383509b8afc90420e11acb3bf6295c4492b4))
- **plugin_management**: built-in groups and default_enabled ([`547596a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/547596ac3bdf7b6818b8dfb2ec91e3d9895a0742))
- **device_viewer**: non-modal live histogram region picker ([`8f93ee7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8f93ee778dfb3fe7dac178313696dd6d08c07ab4))
- **device_viewer**: live histogram region of interest ([`10ce443`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/10ce44353b90f3aa85fbb6778cffdccfabd8b6ed))

### Test

- **image_viewer**: histogram channel mode ([`e38b3b5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e38b3b550ec53fe6e9f4e13bdf79aca2d78b8993))
- **microdrop_application**: follow-system palette fallback ([`14b3866`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/14b3866941c03ceaa5f1d22d93ca236bb186d88d))
- **microdrop_application**: color scheme palette check ([`7e3dfff`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7e3dfff1ff6c0aa51769c4caaca32dd35dedfd38))
- **plugin_management**: built-in group defaults ([`842ebec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/842ebecd2fb573d489a4e2c1129bbf7c71278847))
- **device_viewer**: live region picker tests ([`d762611`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d762611dec7a526d2dabcb4f51e09e489da4cf2a))
- **device_viewer**: live histogram region tests ([`e8d5850`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8d5850c27818d6e0d0a363b259270cfc58a6843))

## [v1.34.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.34.0) (2026-10-30)

### Feat

- **image_viewer**: x magnifier for the ROI histogram ([`74bb99a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74bb99a397260bcaf0c48a40538ed9b5f9bc904c))
- **image_viewer**: decouple histogram bar, fit and fill opacity ([`84d68e6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/84d68e6d6ca525ccabdb0b5a6d03171684c27a7e))
- **device_viewer**: toggle editors for histogram controls ([`eadffd3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eadffd3c60bb1e12a0567c941b4b3754d85ce5c4))
- **device_viewer**: density curve style for histogram ([`6f27790`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6f27790113bc64b266403eba47008fe737dd5d5e))
- **device_viewer**: sample camera feed for live histogram ([`935327b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/935327b77c5c8daa56c6083e9371504c68e911f6))
- **device_viewer**: live histogram model and plot view ([`cfbaa9c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cfbaa9c11e35ced3e54bd108e2065375adc415f4))
- **device_viewer**: camera select-source request with reply and state ([`7b6cb9c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7b6cb9c963ca2d0a35d8eeadd196bff7bbe16fd5))

### Fix

- **microdrop_utils**: apply tooltips on switch/slider ([`fa9cbdb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fa9cbdb7477dfb8e9c14c51c3ab3b8de66f730ac))

### Refactor

- **image_viewer**: hide histogram-only rows outside the view ([`82bbdd6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/82bbdd66e82a3cfe4012b4db2bf508946b1d1bfa))

### Docs

- **device_viewer**: document the Live Histogram pane ([`710a3e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/710a3e8804944c1b922db60419a18af946cb1ac8))

### Test

- **image_viewer**: histogram opacity and magnifier ([`307d564`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/307d5640c5f3084873bf8e1cbac8c73edf43ffa1))
- **device_viewer**: cover the histogram curve style ([`02b2865`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/02b28658569704b72528ed07f4a074ce2a824d9d))
- **device_viewer**: cover live histogram model and sampling ([`d6f0a70`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d6f0a70fcfb4c49bc8772553b1b88c63e68ec3f3))

## [v1.33.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.33.0) (2026-10-29)

### Feat

- **layout_presets**: rename presets from the manage dialog ([`58f6f1c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/58f6f1c6164a6ff0f0b2e341662ea8005a273224))
- **layout_presets**: manage dialog to edit shortcuts and delete presets ([`f9e7e1a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9e7e1adce2f7c5d7aac775eb5403a8dabcb07da))
- **layout_presets**: keyboard shortcut per preset, Alt+N by default ([`74f0fc7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/74f0fc7c6b52ce4a4aa0d137be147f90399e8989))
- **layout_presets**: save and re-apply window layout presets ([`e830717`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e830717e40d920c99e1d42f6722847e93e690403))
- **image_viewer**: histogram intensity range and pixel-count range filters ([`f5a170a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f5a170abc3c064a81a247a09db698bb14b0b501a))
- **image_viewer**: histogram axes, cleanup, distribution fit, marker lines ([`dfb47cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dfb47cf409c33d210cd0ca0e862e635e1e98f088))
- **image_viewer**: per-ROI pixel intensity histogram view ([`bdceaa0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bdceaa0b440ad5b005ab58d84d806c6f7c761e2f))
- **image_viewer**: search box to filter the Experiment dropdown ([`afd78be`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/afd78be84cfa92532ce98522d020e19f977119f9))
- **portable_dropbot**: tray-only moves from the glyph and motors pane ([`8c30555`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8c305554467caf7afa856c8e6eb94ef80b89c212))
- **microdrop_application**: dock separator colour preference ([`4c65ba2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4c65ba2f1b1c1a81289d6a15d049909246747dee))
- **microdrop_application**: color scheme preference (follow system/light/dark) ([`08b2c7c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/08b2c7c9f7e4f829f4a2f7a8ff33a6435d302aa1))
- **rpi_battery_status**: click the icon for a battery details panel ([`218b401`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/218b401e3997a91e827db056229a1e06b1e3ecb7))
- **rpi_battery_status**: status-bar battery icon for the portable rig ([`f4b9830`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f4b983071e8c67ad573dcf362752d9f3b4d3df25))
- **microdrop_application**: File > Minimize above Exit ([`15b04b8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/15b04b8539bbc787dc7b1521d9c094c60b24fcc1))
- **portable_dropbot_status_and_controls**: add settings tab ([`340d6ae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/340d6ae0f5612d73484bd25548627cafce637282))
- **portable_dropbot_controller**: add fan board and chip-detect prefs ([`cb190cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cb190cf1b3b8ac8c2e7974b19e8f8d9adde36a82))

### Fix

- **microdrop_style**: propagate fallback palette under an app stylesheet ([`e7b737d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e7b737dfe1b09e1eaf21d039a60ea243b560cd95))

### Refactor

- **portable_dropbot_status_and_controls**: fan toggle uses pref ([`c770293`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c7702938baba51eef270118e864b6c6a34a8f770))

### Chore

- **portable_dropbot_status_and_controls**: ruff-clean status controller ([`1468f20`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1468f20f47ef0a6a7f2677b3aeae62288884e8ec))

## [v1.32.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.32.0) (2026-10-27)

### Feat

- **image_viewer**: keyboard shortcuts for the ROI tools ([`0a46c37`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0a46c37ef289770e51e4b647125ed352e7964482))
- **image_viewer**: order fastest-change bars by visibility toggles ([`f609f0f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f609f0f4e2af1b0a78ade9318622187623f722c4))
- **image_viewer**: Left Del and Right Del as their own buttons ([`095deb8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/095deb89045141dde7e650254b5c8d1f6b3cefcd))
- **image_viewer**: choose the curve the area fit uses ([`97e3217`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97e32179cfc4cb4c1dd99d527dcef7dda32802df))
- **image_viewer**: exclude images from the area fit only ([`c35f87a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c35f87a2000d29a3d004746e28bdf50f48d6dec1))
- **image_viewer**: area from a linear fit for area-normalised stats ([`f0d4272`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f0d42727283bb8b2783e88c4ece88f35e156c07f))
- **image_viewer**: font size and bar gap figure settings ([`19a1da5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/19a1da53a72d077acbfc08c26a939d5dd86e2fe2))
- **image_viewer**: zoom fastest-change bars to their spread ([`92134e4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/92134e44a5f48ea0094f1d82ec8092756d354df4))
- **image_viewer**: clear scale with a length of 0 ([`e0d3b8e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e0d3b8e0bea99c685ac076e509111c69e846126d))
- **image_viewer**: delete ROI button on the analysis toolbar ([`8e6e524`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8e6e52410a7c5e7bbba0aa7971a09f3c43854424))
- **image_viewer**: Left Del / Del / Right Del delete scopes ([`356e538`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/356e538586cf5b34bd52d45ebbeddbebe2689cc4))
- **image_viewer**: Trace rims button beside Track drift ([`a6eb8e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a6eb8e899f5f1cfb15fde23c2004ef36b0e5daa9))
- **image_viewer**: rim tracer traces droplets by their bright edge ([`1078560`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/10785608231ca696f4741edc28a09544490604c5))
- **image_viewer**: measure only the inner part of each ROI ([`a158052`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a158052e88d864d1fdd04a977d18ee00c3a7152f))
- **image_viewer**: size window gates the drift tracker ([`e75f7d2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e75f7d2e82367ec95741c2118eaee7aeaa7276b3))
- **image_viewer**: allow ring gaps up to 500 px ([`de1bd46`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/de1bd4622f2d1fc6dd9820ab55feb2823a8fbbb7))
- **image_viewer**: the table's eye hides the ROI on the image too ([`7cfaa11`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7cfaa11f29307ca173edaa850233fb54b02af01c))
- **image_viewer**: delete an ROI everywhere but the shown image ([`4457938`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4457938dee9094871c9fea8ef7923a69119a0304))
- **image_viewer**: delete an ROI from this image onward or backward ([`869d87d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/869d87debced37fb337b8a7dcfcf9f6311a4596c))
- **image_viewer**: replace an ROI's shape on one image by renaming ([`427bcde`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/427bcde30feb3fb0dec1cfcd65ac525466f2c50a))
- **image_viewer**: single-image ROI geometry overrides ([`c2316c0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c2316c0c55346777efb245ede7dc424581aef910))
- **image_viewer**: remember the ROI delete scope ([`b90307a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b90307ac32edfc5a11494c93d1f8f8baaf3dfa0d))
- **image_viewer**: delete an ROI on one image only ([`3fec6be`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3fec6bea86ec543001fa066a3741b7a25585d57c))
- **image_viewer**: alpha for the temperature plot's line and markers ([`5bbe691`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5bbe691743715acdafd23d2ba68fcc000d152e74))
- **image_viewer**: style panel for the temperature plot ([`ab2e3a6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ab2e3a6b9eb996a6f1e9f1f5ea59062913eeed95))
- **image_viewer**: temperature over time plot view ([`9d32170`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9d3217057b3f9517513a30d6f25dc871edb1df47))
- **image_viewer**: include every excluded image at once ([`55984ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55984ac6baa77a30848d44fdacd3b75ba7b27282))
- **image_viewer**: toggle for the excluded plot points ([`6f46031`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6f460312cab010c48b26228e426fa7281cd6807c))
- **image_viewer**: click a plot point to exclude its image ([`1deec8f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1deec8f9a5dccb105778e9045d71e83f7cc3ac69))
- **image_viewer**: choosable time units on the plot ([`ac5c696`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ac5c69606091fdac1af7d585e98e0aef50295617))
- **image_viewer**: protocol step and frame x axes ([`cccaba5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cccaba5187c1807785026513c74d39a7660919ea))
- **image_viewer**: area-normalised mean plot stat ([`5e40e15`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5e40e155bac0ec82512a092469189258459ce5ab))
- **roi-plot**: copy the trend expression for the compensation ([`91db18a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/91db18ae27f7c2380c1b6d4999543bb6ccddd36a))
- **traitsui-helpers**: live tooltip for IconButtonEditor ([`efe081a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/efe081a729b524c5b8776ef937a2e772e291f247))
- **roi-plot**: calibrate the temperature axis with actual = f(expected) ([`aad3e8c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aad3e8c3a2e599d38f7e45f26a5429ada60c5b18))
- **curve-fit**: give every fit a full-precision expression ([`5838a75`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5838a75e8444968131ad7be485630d63aac0aa69))
- **expression**: invert a function numerically ([`eed39e9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eed39e94575d0ccdf2f7cf6f0479e7547c09067f))
- **expression**: parse parameterless functions of x ([`fb065e3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fb065e3b83f704000aa987efcc0ed34b5cddc114))
- **device_viewer**: keyboard shortcut cheat sheet and tooltips ([`ab041eb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ab041ebe2826111aa337a83a3b9c0496fb769458))
- **device_viewer**: draw routes with Alt+arrows ([`6957b0b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6957b0bdd67862ec1d099edd7c59eabcff620792))
- **device_viewer**: keyboard shortcut service ([`260351a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/260351afe08f210da22f1be741d1608eafcc6b77))
- **device_viewer**: declare the keyboard shortcut table ([`e42b6f3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e42b6f3f52d43dbdc62684d49a9267de36a4f4bd))
- **protocol-tree**: insert step/group above a row ([`364188d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/364188d39ca42c0d3f2664e834817256e6bd69be))
- **image_viewer**: extend actual-vs-expected view ([`cac195b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cac195b244e7e701697642537e970e757fa2dfa4))
- **microdrop_utils**: multi-cell table copy and paste ([`f3650d3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3650d3d6f8201566b5b5e859bc6a8829210afc6))
- **report**: outlier filter and section folds ([`1139620`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/11396205a28378fab59550413743af9c125673ec))

### Fix

- **image_viewer**: refit plot margins when the font size changes ([`f7cb3a6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f7cb3a660e4414e0037f03b1d659217cdf0339cd))
- **image_viewer**: tracked shapes keep each ROI's own kind ([`4617f45`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4617f45085a296773a3fb1e8c259e011779a94fb))
- **image_viewer**: shown excluded points set the time origin ([`e1c8e2f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e1c8e2f5abcd8a5086ce0f398f27def2bd454059))
- **image_viewer**: merge ROI definitions per image ([`7df6381`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7df6381634c8465ee6ac5f56b2dec6e08195235d))
- **image_viewer**: merge ROIs on a name collision ([`a2aa76a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a2aa76aeba015b602d1569e5c2e1ccc05055b5ea))
- **image_viewer**: drift tracking follows per-image ROI corrections ([`bebf790`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bebf7903bc9e04dbe465c8f9ac7ca913f6dc909d))
- **image_viewer**: clearer area-normalized stat labels ([`031e240`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/031e240efccd6b855008529a85b81cc15972c8e0))
- **protocol_tree**: report a missing channel map once per run ([`ac8d740`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ac8d740b71bf8b0eb5a5c45d73653ddd0b4896b8))
- **protocol_tree**: keep device channel map across protocol resets ([`ba42fd4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ba42fd411b35ec1806679d22a1abd5e1b6d66e73))
- **roi-plot**: copy the identity trend as x ([`02e2f74`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/02e2f74338b6ecd70a9b09408c5cf19c8fdcfc8c))
- **device_viewer**: keep Find Liquid out of display mode ([`f133d70`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f133d70d1a1b685608569d843931ab4cb77ae6d3))
- **device_viewer**: accept keys the shortcut service handled ([`723ef1c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/723ef1c80f19c65f422fb52834307a9c4a890762))
- **device_viewer**: route erase built routes positionally ([`e53b4b5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e53b4b563dbed437a227f9ef7fd1d8b4223307f5))
- **device_viewer**: endpoint erase looked up the route on the main model ([`e473ca5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e473ca5199a1ba3818f16cf095b5adcd2da0a6b0))

### Refactor

- **device_viewer**: share the keyboard shortcut helpers ([`1297219`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1297219758a1ba261ef41dd167ff9081ca20f682))
- **roi-plot**: fit the Actual vs expected trend in the model ([`c91ba28`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c91ba28a71f21d388d45784f522e03790f4ab8f2))
- **expression**: move the equation parser to microdrop_utils ([`e5c092b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e5c092b638fce5f0846f2aec2fdaddbc3a2a90f3))
- **device_viewer**: chunk the electrode scene handlers ([`4f1ffcd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4f1ffcde8cfb7be887525ad5b30ffe2c47f2179d))
- **device_viewer**: route key events through the shortcut service ([`c52bada`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c52badabf34607d497a4f559c2d4b413d26a49a6))
- **device_viewer**: make neighbor_in_direction public ([`9505fe6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9505fe640034f27f1aad34e09718a4ba60d921ca))

### Docs

- **image_viewer**: README shortcut table matches the Del action ([`056eb50`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/056eb505ee6ee83f46ae5c03a16738e780f8974b))
- **image_viewer**: Del shortcut deletes from the shown image ([`9fe1860`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9fe186071a0f2e3024bf34dffbd255e3c7086232))
- **image_viewer**: Del asks Left Del / Del / Right Del ([`b03eede`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b03eede6e0fd68e08f13d538d9a8b1c7d8b721d0))
- **image_viewer**: Del asks which images ([`7314490`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/73144905591b1b42a9a827dfaebe8df98b1096f2))
- **image_viewer**: describe per-image ROI deletion in tooltip and sheet ([`4747b3c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4747b3c707adcfd04782182af166eb07ceb7f016))
- **image_viewer**: say how the fastest-change bars are ordered ([`e40b97f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e40b97f8362f15839f99faf782ddfda0fdc7e0e3))
- **image_viewer**: help rows for Left Del, Del and Right Del ([`d880aa6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d880aa6a37b8c662c2cc28ac4f5d6aecf41288b0))
- **image_viewer**: explain the area fit's curve choice ([`7354420`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7354420579bbf3f311f5cab2d06224a0b6e54a5e))
- **image_viewer**: explain the area fit and its exclusions ([`089ebf3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/089ebf34c8f3bb8519ff9c426459c3c7d90ec2bf))
- document the device viewer keyboard shortcuts ([`0706d1b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0706d1b71ff494ed644288ad0e0e45ef3c18da04))

### Test

- **protocol-tree**: cover insert-above placement ([`cc0cdba`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cc0cdba42c9e709d41a7d51c0d8d998bd5705607))
- **image_viewer**: cover expected-view extensions ([`b5a7f9e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b5a7f9eac1fd2fd717b9f07cc788952c76881a99))

## [v1.31.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.31.0) (2026-10-16)

### Feat

- **protocol-tree**: subtract the filler calibration from dielectric thickness ([`caf1bd7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/caf1bd77e9dc3a71a0f2bcf3b28f59d15b66e49d))
- **protocol-tree**: collapsible trend charts in the run report ([`2e9adec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2e9adec1d4083311e5c9cfb2666f80825cfc500e))
- **protocol-tree**: log capacitance over area and dielectric thickness ([`5d97a1d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5d97a1d751eca95075defdf8c8cf63f902b7423a))
- **status-pane**: publish the dielectric material to app_globals ([`fa4b907`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fa4b90723dc5037715a931488bb29cd301303bb1))
- **microdrop_utils**: import the package after update ([`b4607ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4607ac0556d570099222426feddc7faa6d49233))
- **microdrop_utils**: warn about the branch switch on update ([`8e8bba5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8e8bba5d4a06c5d7b91dcc55d308cf206110f5d1))
- **microdrop_utils**: demo the update dialog standalone ([`ab55047`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ab55047f2a932bd46d249c63c3eaba3246336cca))
- **microdrop_utils**: reinstall plugins on env update ([`b223478`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b22347855062909197f88097955e053bc8618c0f))
- **image_viewer**: tidy the viewer pane layout ([`d1b4794`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d1b47941267fea49e59fd5a39f9e998640145b9d))
- **image_viewer**: send deleted experiments to the trash ([`86a5646`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/86a5646bb7162c2b6cc735f4f9dd918ed2f3613e))
- **microdrop_utils**: shared environment update and relaunch ([`2193d85`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2193d85d1ae2775de86ef5b560c88fd3383ac0e5))
- **image_viewer**: undo and redo for ROI shape changes ([`e929a8b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e929a8ba53c82432b163bfa36dd4d6b52c9fb5da))
- **image_viewer**: toggle to show or hide ROIs ([`7837ab2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7837ab28297c41653e5919151be83b9086b33e55))
- **image_viewer**: add negative ROI masks ([`658cb82`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/658cb8236e539b2713ce1ddf1fedf5121721652b))

### Fix

- **microdrop_utils**: rich-text wording in update dialog ([`8cea964`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8cea964832b89cbcf2dd36afa5118df72c1d9827))
- **microdrop_utils**: check out default branch on update ([`0b67ffd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0b67ffd74e36e6d02f8f31f548370ab33953f8a4))
- **microdrop_application**: escape ampersands in dialog buttons ([`0dd2db4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0dd2db473830142a1fd3dd26e4f860820e437d22))
- **image_viewer**: resize the viewer pane continuously ([`c46bd5d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c46bd5d4c0660ba9e9c6c8e6a08b12ae12368025))

### Refactor

- **microdrop_utils**: drop relaunch from env update ([`6ed4a0a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6ed4a0ae1c010198fe99c6242181fc1306ed079c))

### Docs

- introduce new UI dependencies via env update ([`97a438e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97a438eb685c1d650e3fc6d03d8a1ee45ff39ea8))
- **report**: filler-corrected thickness and its footnote ([`32f6679`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32f6679f6289b12d1c156b150f1e8b8c61b2d965))
- **report**: document the dielectric columns and folding ([`8889acf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8889acf92b7b15625aa4ee779a5a1215518ccd3a))
- **report**: explain the Actuated Area error bar ([`959084c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/959084cc20dc69ac367044552c06deb4f3ee705a))
- **report**: spell out how the trend error bars are computed ([`8539c2b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8539c2b4c9cfc3e4f1a09641bd0eb87ebdd7793d))
- document the protocol run report pipeline ([`fab14b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fab14b0f8d10afe16ed21c819b9d3c17a86eb60b))
- **image_viewer**: align the analysis tutorial with the pane ([`ffb4712`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ffb4712f5d12cce7347244dcb866b0b8f3449535))

### Test

- **microdrop_utils**: expect rich-text plugin list ([`e8a74de`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8a74de3154b7848d7ca999ca1e428bc7861306f))

### Style

- **microdrop_application**: format dialog base with ruff ([`63db236`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/63db236f1c067737b4a304dbcce5bbec73d05120))
- **plugin_management**: format package installer with ruff ([`aa47f4a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aa47f4aa30c43338b6f043a8cddc4c3aae0aa500))
- **microdrop_style**: format button_styles with ruff ([`97b8ebf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97b8ebf64ddc7770e70e2e5f986b489432a07453))

### Chore

- untrack superpowers specs and guard the dir ([`6b1f239`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6b1f239cf4d80b8e49b58a62cb84cbb0d9057a9f))

## [v1.30.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.30.0) (2026-10-15)

### Feat

- **image_viewer**: standalone metadata panel demo ([`be7386b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/be7386b89d97680cfe45ce9af08408e576d429d9))
- **image_viewer**: file details and described metadata fields ([`b363233`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b363233ccc8761970c0b98d1cdd9fef2c59b2b08))
- **image_viewer**: rich-text metadata widget with tooltips ([`63830ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/63830ac1a071782bda8ee165b298c6733135b585))
- **image_viewer**: metadata as a rich-text table with a pop-out ([`4c8918a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4c8918a6a20e61b16118d83e7f594664669abe66))
- **image_viewer**: collapsible Metadata section for PNG text chunks ([`7d90bf0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7d90bf086eb9983ee257183d932dc36d1a062bbb))
- **protocol-tree**: add Open Experiment Folder action ([`5fb6935`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5fb69352353e182d070906a87a3eb5160aecf3e8))
- **image-viewer**: add a Prune Experiments action ([`5bb3315`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5bb33158b171dbc8d51d6016657b1ecf79ad6532))
- **image-viewer**: add experiment pruning helpers ([`4e91265`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e9126589e729feac25eb1e2cae64a5883f2e197))
- **image-viewer**: add a d² zero marker to ROI plots ([`47b06ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/47b06aca9c95f514df96d990c5d2e13008187fdc))
- **image-viewer**: export the Expected table as CSV ([`82e3ea5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/82e3ea575465b508b83ecf20983de7804800fe3b))
- **image-viewer**: flip actual-vs-expected axes ([`6007a4d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6007a4d3f296aef31d57f71882fa8d8e281196e6))
- **image-viewer**: plot actual vs expected ([`ed315f5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ed315f59f6d0b48f3ac779cf51e7f3cc079966c0))
- **image-viewer**: set an expected fastest change ([`585436c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/585436c0a158d2adc81d0a766def4ff998cfda77))
- **image-viewer**: add a 1st derivative ROI view ([`549e4bb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/549e4bb0fa6ef1d925bf091cb9c93c14f9e23db9))
- **image-viewer**: word plot labels by the x axis ([`bc84568`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc845684331db0abf1e0e29eba7d314b97452c57))
- **ui-helpers**: hover combos take labelled dicts ([`60ae71a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/60ae71aeba999a7f9deafc5cef168b250dd4069c))
- **image-viewer**: add a delete-experiment button ([`56fbce9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/56fbce9616ee3b1d621e09db350920bd73d2ef13))
- **image-viewer**: add delete_experiment() ([`8e2e8e5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8e2e8e59645209d08abdceb89ff788a23a698862))
- **image-viewer**: calibrate the temperature axis ([`4533177`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4533177e306f09ad49b4ea2893e269c6e4a2e32f))
- **image-viewer**: add experiment seek arrows ([`5e7647b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5e7647bec85507bb48eff01770842e964bf4b662))
- **protocol-tree**: write viewer edits to selection ([`0b7ba36`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0b7ba361f54df7e6226430013cca61cb664fe80b))
- **protocol-tree**: fill electrodes by channel pattern ([`3ac8e83`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3ac8e83609c6d0d0e6769c2e49e589f50e98c1ac))
- **protocol-tree**: add a device channel picker ([`5cd6504`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5cd65045681747f4c4c279d94bdc3bc71e5be2fe))
- **device-viewer**: move gamepad preferences to the plugin ([`8f7beae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8f7beae712434ae36fecc946e9fcf702c0b2e573))
- **device-viewer**: warn on a layer contract mismatch ([`f6849b5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f6849b54ae2b0b24a9045ea43e96439a22a3208f))
- **device-viewer**: add the IElectrodeStepping contract ([`b33d880`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b33d880f3b8ee7b6f3d9ceb0d073e91a1e520e5d))

### Fix

- **image_viewer**: scroll the sidebar on its own, wrap the metadata ([`364a65b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/364a65b3ed27945b9e10379ff688d71c8005a693))
- **image-viewer**: keep fastest-change actuals current ([`ae91375`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ae91375864a7719f8b1ed929dcaf70a0cd2e1cb8))
- **image-viewer**: size plot controls to values ([`e6315c9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e6315c9fb0530a11c95045029a465af92bcd24fa))
- **protocol-tree**: sync viewer on electrode edits ([`c89620f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c89620f725af1a96fbbe04a239e57c3a927fe0a5))
- **device-viewer**: keep app start alive if the gamepad move can't save ([`bfa5329`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bfa5329c5769fe93cd8e2cb6086f1ec7be819a8e))
- **message-router**: sweep listener queues of crashed sessions ([`517d5f6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/517d5f66328ceb142c58bc69594b293be8e5bcd3))
- **broker**: tie spawned redis-server to the app's lifetime ([`91003be`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/91003be3385c4557bf14bad9001926745572ddad))
- **image-viewer**: correct win tooltip and scale docstring ([`41dec03`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/41dec031233df012b895a3701b5110d3e79456b6))

### Refactor

- **device-viewer**: declare the Device submenu groups ([`32190ab`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32190ab6353e292acb8d62517df7c196b9be95d3))
- **protocol-tree**: group the Protocol submenu ([`9f45fff`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9f45ffff4bf30e169b9974d4900b7633e8bfbf48))
- **app**: one File group for the submenus ([`0434ab0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0434ab0f353cf0b52ef15a3943481daa5c4b3cb8))
- **protocol-tree**: add an Experiments menu ([`88462f9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/88462f95167705648b4932c5f4e30613453db67a))
- **app**: add fixed File menu sections ([`ad25d2b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ad25d2b54d1aa784e6514765d02e58c603ba489f))
- **image-viewer**: share the plot's fit loop ([`9931d50`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9931d504ae8119d8b8c9e74fdabcf75e43029580))
- **image-viewer**: share the experiments root ([`03ae17a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/03ae17a937ea7f9bd35a99e1474bf857f57821ac))
- **device-viewer**: move gamepad support to its plugin ([`e92682f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e92682f1b8d97aca53b39641d2f3b61160624956))

### Docs

- **messages**: note multi-selection write-back ([`292f8bd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/292f8bde8231e22139c766229cda16d8df3e719d))

### Test

- **protocol-tree**: follow the grouped Protocol menu ([`cca4c56`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cca4c5664bf5ab8cc470829c0b0db554f1626fc5))

### Style

- **device-viewer**: separate the status-bar early return ([`e5c96bd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e5c96bd7c40021daaa21dffedda01ed4fce6f3ee))
- **utils**: ruff-clean dramatiq_pub_sub_helpers ([`4297946`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4297946167f4dacca83d811bd3eb54a37f52dcc6))

## [v1.29.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.29.0) (2026-10-08)

### Feat

- **protocol-tree**: scroll the quick-action bar ([`6a08562`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6a08562fbfa86ed458e2d81a75d3b56067a19cb8))
- **video**: camera lead time cell on Capture ([`5407309`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5407309d07ac9e61568c92bd571c1a4e379ecccd))

### Fix

- **video**: wait for the capture ack before the step ends ([`025b761`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/025b761d38cf2a60be0547942f6106a506ded40b))
- **video**: let the Video column publish the lead's camera-on ([`9b35997`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9b359972e318975ef0d9d67ea228d3fc826cdd32))
- **video**: keep the camera on across lead-time steps ([`2eddf46`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2eddf46cd16e3cd5bfb42bf700279fd5d6b5225b))
- **image-viewer**: make the viewer pane scrollable ([`a4f611b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a4f611b9256f013636a46c81060ab6a3f87123e9))

### Test

- **video**: cover the Capture camera lead cell ([`6bb4db9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6bb4db9c2b89f87cb24ec2cd7ce6e3525f4971a4))

### Style

- **protocol-tree**: ruff-format quick_action_bar.py ([`71b55c8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/71b55c84e1e822b934d5e1803658b8ab76bf8374))

## [v1.28.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.28.0) (2026-10-07)

### Feat

- **image-viewer**: run analysis lighter during a protocol ([`c08d858`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c08d858b19dcf57d0db2545b12bec980754bd0e7))
- **image-viewer**: hold the view under a draw during a run ([`0febfd3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0febfd3e42e56e4dfae92e4fcb546e44f816bcc8))
- **portable-controls**: chip status readout and alarms log ([`949272d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/949272d478cf5864281556692d2ffd4c1b75cce6))
- **portable**: publish the chip pad contact mask ([`57e55af`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/57e55af83319c8847220234ead1d31727797b3ab))

### Fix

- **image-viewer**: tail heater logs off the GUI thread ([`44cf566`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/44cf56602a8299d590b42d753b16c8265c53eb43))
- **image-viewer**: rescan while capture files are held ([`9c50912`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9c50912613af2ccc06dcad82bb3d56574ce52e61))
- **image-viewer**: skip capture files still being written ([`0995c9d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0995c9d6d20bd6ba23556c7321512fc3682df4be))
- **image-viewer**: render display frames off the GUI thread ([`da43cbe`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/da43cbe06830c9bcf92e8532772044fced8f045e))
- **portable-controls**: name the pogo side in the chip status ([`41c1548`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/41c1548c88480aab2bd4bd5d93b8b0438376122e))

### Perf

- **image-viewer**: coalesce the pixel readout repaint ([`786e99c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/786e99c9867f54ec5f099773a1588453fcc706b7))
- **image-viewer**: walk captures once, off the GUI thread ([`cf7c9da`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cf7c9da659b772f24a357d64162cdce4a94cdc8e))

### Test

- **portable**: expect the pad contact mask in the snapshot ([`f719bb3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f719bb3edecae62d9dd54e6415c85873b214f53c))

### Style

- **portable-controls**: ruff-clean the status view and handler ([`44b82f0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/44b82f047a3b87ef602e35079b20e0eaff984460))

## [v1.27.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.27.0) (2026-10-07)

### Feat

- **protocol-tree**: Fill Pattern button, shortcut and grouping ([`4cf5076`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4cf50765880c43f888b4ebc3403f3c9a9fe8032e))
- **protocol-tree**: Fill Pattern dialog for step runs ([`54f64d6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54f64d617f404ba319950da4647c11c950d44d38))
- **image-viewer**: extent and orientation plot quantities ([`978bd37`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/978bd37c1001e18a46af580d8f0e79b563b7085a))
- **image-viewer**: eccentricity plot quantity ([`bd20c67`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bd20c67ea8e4ed76d67c45d95f259d08a43f5ea6))
- **image-viewer**: circularity, shape change, axis ratio and solidity plot quantities ([`ee557c0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ee557c0dcb9feae989d9fd0827cf3877a631a160))
- **examples**: shape-moments runner and findings ([`ff0127c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff0127cdc1c1ec1759ddad4319dc5aa83bbc9c3e))
- **examples**: shape-moment descriptors prototype ([`b1f50fe`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b1f50feb3946b7287982f0c911f6aff3e1a5c0eb))

### Fix

- **protocol-tree**: bulk-set every compound field ([`ae7fae7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ae7fae72b11b53c87df5ae33762551497c65f168))
- **status-bar**: seed the device icon from the live colour ([`6409ec3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6409ec3907d684f58870df7a4f62c139b21c464d))
- **portable**: resume status polling after connect-on-port ([`0c9c1ce`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0c9c1ce0c30d4019cbc29dc0c80ea854c23cf191))
- **portable**: read chip_on_pad as a contact mask ([`0e1e10b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0e1e10ba868e841d4433dd2fef560ea99640fe4f))
- **device_viewer**: align provider camera feeds ([`a171cb2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a171cb2d124a1ef8aefd8bbc19a1e8cae4006dfe))
- **image-viewer**: search sibling heater logs only from the default folder ([`63eda06`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/63eda06ce903946da7a966f7eae322aa3691247c))
- **image-viewer**: explain missing heater-log coverage ([`4655a2e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4655a2e8b0a37340c89a95f5ee395e3f693fc1b7))
- **image-viewer**: find heater logs in sibling experiments ([`3aaf0bf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3aaf0bfd9aadc7a1ac3ad7950066e183cec8e7fa))
- **image-viewer**: name the help entry Image Analysis Tutorial ([`aaf9c37`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/aaf9c377f01189c1bacb008b87edf86765e3dccf))

### Refactor

- **protocol**: drop unused camera prewarm preference ([`31c6905`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/31c6905859a6e92e7fe984ba773acdaeb6077110))
- **protocol**: drop stale capture_time preference ([`a85f1cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a85f1cbd4c8a24b353b80d08670b8ee3a0c8312b))
- **image-viewer**: shape descriptors as an analysis module ([`b4b2c0a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b4b2c0a8c100ce9ca29ef161018081e0ed0a771d))

### Docs

- **image-viewer**: static pipeline diagram in the help guide ([`9fcf3f5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9fcf3f589b5e7f8ee6a827f9291101f806b219e9))
- **image-viewer**: colour declines red in the shape demos ([`c3a115b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c3a115bc5fefbb644c04f9231cfee5d41f1ff586))
- **image-viewer**: interactive droplet shape section in the help guide ([`82b9541`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/82b9541be74ed2c232a2a43f3ac7a37539c09eef))
- **image-viewer**: explain the shape quantities in the help guide ([`3bdbd47`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3bdbd4774f40bb63ed9161faab205dc8de9f1209))

### Style

- **quick-actions**: ruff-format files Fill Pattern touches ([`99ade39`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99ade39dd6ac1fae6a209ef1ca4c85e8931cc41f))
- **pluggable_protocol_tree**: ruff-clean consts, preferences ([`cba6636`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cba6636a7d9409e644635461fa5e7ae0d163c472))

## [v1.26.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.26.0) (2026-10-02)

### Feat

- **device-viewer**: reset buttons in both alignment panes ([`4e34b14`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4e34b144f94171a4de9b69cef38d798771734445))
- **device-viewer**: lock the camera image while rotating or flipping the grid ([`041aaaf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/041aaaff2dfe5c5d275ea0b76a39039b62458516))
- **device-viewer**: start both alignment panes on the same TL/TR/BR/BL grid ([`0780017`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0780017127eebc1b8abe3291d7c71dd2a33c44f9))
- **device-viewer**: dot-number alpha in the alignment sidebar ([`c79c698`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c79c6986dcc8109a53abb05143b063482920d1a0))
- **device-viewer**: number the alignment dots and warn on mismatched order ([`7d2b873`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7d2b873cf653f76ae147782b71adc3cf9e84fc88))
- **device-viewer**: alignment highlight colour, alpha and size in the sidebar ([`8d2f6d2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8d2f6d2ec8a9c8ea7a9c6a7796416719fb17de7f))
- **device-viewer**: highlight the matching alignment dot in both panes ([`9091cd0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9091cd02f259c783c40d4e36211ff3b34c7dd4ff))
- **device-viewer**: rotate and flip buttons in the alignment dialog ([`5d51cdc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5d51cdc5a2210177fcdb6cc603700e11ab6ff5d4))
- **device-viewer**: flip the camera image in the perspective model ([`1a103de`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1a103de19d00effa22aa9a48f1f4bf4d3a45e484))
- **image-viewer**: toolbar icons, plot examples and walkthrough in the help guide ([`0e14541`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0e145419998a5a34b253e71ad034caf200c5eae8))
- **image-viewer**: open the analysis guide from the Help menu ([`f121de9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f121de97a09bdaa3a5b13a4046c295d9789128fe))
- **image-viewer**: add the analysis terms help guide ([`8823a75`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8823a75e774ad7e028e67083b4f246ca4d15e506))
- **image-viewer**: device outline reference in the transform pane ([`7015dec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7015dec0fa4d60ee99bfdb62c144ed3bd0e0ae50))
- **image-viewer**: add per-image and distribution views ([`6af7c80`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6af7c803d1eef1b708ee427ad6fa79de2c7d5be3))
- **image-viewer**: offer ROI area as a plot quantity ([`fbe034a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fbe034a783602127b51cbedb8bfabbe87b4e4d84))
- **device-viewer**: host contributed layers ([`931ac26`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/931ac2687f13d6635b53756efeb46a716214a8d1))
- **device-viewer**: add the layer contract ([`079f220`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/079f2202e1fe4329779e11e04c546666b23f2dae))

### Fix

- **device-viewer**: a freshly loaded device is not modified ([`b282dae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b282dae66350c9c6afb4ee76de45753cccd9842d))
- **device-viewer**: let the endpoint reset prompt pick its parent ([`f3e9be7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3e9be7a8874824b0b35e792a76d6129496ed79d))
- **device-viewer**: store the alignment cache under application_home ([`382a016`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/382a016c51399f09a069d20883b4099a6462a3bc))
- **device-viewer**: always number the device-side dots from top-left ([`8940a9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8940a9b9e5d281323bd892897a05f477201ef895))
- **device-viewer**: generic rotate icon in the alignment dialog ([`f3654cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f3654cb4a47bd6b7c4e06718b7e670249f37fd54))
- **device-viewer**: respect quadToQuad's failure flag ([`42b8e42`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/42b8e42d726d225d79717cb6bcff8530bac65adf))
- **device-viewer**: isolate all model app-globals in tests ([`9743688`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9743688c2e53ef141c9d6a99cdde18793cb49d15))
- **image-viewer**: use the device viewer's perspective icon ([`63aedbb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/63aedbbd7574cb9e2f97934f45d96ba4c4364942))
- **device-viewer**: keep tests off the live repo-dir global ([`0035224`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/003522487ad17c717135dc9107b0e8c3d9845c58))
- **image-viewer**: keep ROI names on fastest-change bars ([`b5706cb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b5706cb30d3f9a8449671bdb718359b936e9bb72))
- **image-viewer**: show full labels in plot combos ([`c1e845e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c1e845e07b036e23b963edac1d5bbffb5994afe0))
- **protocol-tree**: fit the Protocol Has Errors buttons ([`643f0f0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/643f0f0f37fbb0051b7dcbb57d87bf288924a279))
- **protocol-tree**: route Bulk Set through the column handlers ([`803be13`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/803be13f6b70fed31edf74dc85df1a2b9cf301b8))
- **protocol-tree**: honour the full-timeline toggle in duration mode ([`1b56346`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1b563464070cbe701fc3225aab8efa2ca1cd534a))
- **protocol-tree**: route reps and repeat duration take over by last edit ([`68f087d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/68f087d6ce22db7911742a6cf317eebda752f8cd))
- **protocol-tree**: refresh the timeline on cell edits ([`5f9c309`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5f9c30906ffb76c1c2ede172ee907854528eb96e))
- **camera**: deliver preview frames on the GUI thread ([`62f7e45`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/62f7e45333eccef9d9a05d6cba2d598608a7f119))
- **device-viewer**: recover from undoing the camera rect ([`9be2e92`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9be2e92f6f3a25579e5432a920b76b38a82f943a))
- **device-viewer**: stop publishing an empty geometry map ([`3205369`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3205369cc5fe71aa7d05749f2afef7c3b4864a3b))
- **device-viewer**: stop layer host test leaking preferences ([`748fe59`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/748fe599c19460538ece78dff26233e61d5a79a2))
- **device-viewer**: guard layer host and alpha observer ([`f6215fd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f6215fdbb27ce0bc474b6999b124d0e3a37b5069))

### Refactor

- **device-viewer**: move SVG persistence to a service ([`a2073d4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a2073d405b36f041c979e0cb2f664d87a4b75d1c))
- **utils**: share the zoomable graphics view ([`99c67f0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/99c67f0df8138029e268702ec16b45f68f4a2a1c))
- **utils**: move SVG outline extraction to microdrop_utils ([`e5d979f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e5d979fd20e722a70da871aa22aa7b268c8f623b))
- **protocol-tree**: split RowManager persistence and clipboard ([`04f9d13`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/04f9d13ca9a1990fc659bda2babfdaa8c5949b4a))
- **protocol-tree**: move column rebuild into RowManager ([`ee4be45`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ee4be45187933795d06d1e973f9e7ea17517614b))
- **protocol-tree**: extract repeat-duration reconciler ([`d769b12`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d769b1262e54a1b256e7f8b2f94f3b47ea5b10f3))
- **device-viewer**: breathing room in publish controller ([`9644001`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/96440015af4c173962bc65a76207b2908d005150))
- **device-viewer**: move outbound publishing to a controller ([`fa52130`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fa52130bd852fb32e73fce70c47d0d44b48593a1))
- **device-viewer**: tidy sidebar assembly out of create_contents ([`638531f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/638531f6dce3b3339b44d780be41c03515202c58))
- **device-viewer**: move sidebar sections into builders ([`5432359`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54323597e535f93aade78d44aaec4d74cc9004fc))
- **device-viewer**: build recorders in recording.factory ([`d61c4f1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d61c4f16953ad8ce84320708daec58e75d2ef431))
- **device-viewer**: move the media-capture cache actor to services ([`9751040`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97510403467fda61dbf80a705f3252ce656ddb40))
- **device-viewer**: split utils/camera.py into capture and recording ([`c069515`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c0695150087deaf56513445ead7391a6ee62f125))
- **device-viewer**: extract CameraController from the camera widget ([`e163432`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e163432dc5321c2aea6f5a593fb5baa9e3cdec29))
- **device-viewer**: move camera widget state into CameraModel ([`5880787`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/58807878a36daba32d4f0f78a31812549db282a9))

### Test

- **device-viewer**: cover the publish controller ([`5a56426`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5a5642609cd4ac20ce411295279234e67c59f730))
- **device-viewer**: cover the layer contract and host ([`7d03354`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7d033540223c572e8063a7c2ba059c19e76b9314))
- **device-viewer**: cover the sidebar host ([`9ace435`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9ace435fd1525be4362d869d477ca713b914d430))
- **device-viewer**: cover CameraController with a stub camera ([`d8db3be`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d8db3be6ca45120adfcbdc1122f3951c3ed34ece))

### Chore

- drop the legacy MicroDropNextGen application home ([`4940347`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4940347484919821709b1d5878c1589bef493473))
- **examples**: scripts that regenerate the analysis help figures ([`3131429`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3131429a0da4b093f9868769ddf948d24136880e))
- **protocol-tree**: ruff-clean row_manager.py ([`f76ccae`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f76ccaebc3d97d3bba96737d0d0a6d658be765fa))
- **device-viewer**: ruff-clean the plugin module ([`0e06f56`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0e06f56052ce9b547376737bc6f0d0d0d547e311))

## [v1.25.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.25.1) (2026-09-30)

### Fix

- **device-viewer**: harden the moved message handlers ([`ea043a2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ea043a2c7932da25d9b9b0d56f34d8bbb029ea21))
- **device-viewer**: reset the apply-state guards in a finally ([`586fc64`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/586fc64db18c3188295e8a8ac16696b19c0ccb35))
- **device-viewer**: never leave the undo guard latched ([`5ed4d8a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5ed4d8a0debfdb5ad5ed0644449a55b38a70f77d))
- **device-viewer**: disable Undo/Redo when nothing would change ([`422c257`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/422c2572965744162ce637d9d4bd0ed0e532aaa7))
- **device-viewer**: undo against the live container, not a stale one ([`7d3e390`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7d3e390370f73b5dfac776291790db9340bc6d2d))
- **image-viewer**: sync the env when installing AI support ([`772a499`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/772a4993e81fef6d777566712a0fbfce7fda87ec))
- **image-viewer**: stop co-installing onnxruntime-directml ([`a7d9088`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a7d90888e24f9bd08cb48a21b27221d66f09b9ef))
- **image-viewer**: survive a broken osam install ([`da53085`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/da53085fb8ab5482d2dc999eb800efd640bfbc06))

### Refactor

- **device-viewer**: tidy the message controller ([`4887e90`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4887e901000144be4972ebd0fb6dcdff2c08d926))
- **device-viewer**: move message handlers into a controller ([`d324a50`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d324a501d2b242dc501dc17260bf15d489d12164))
- **device-viewer**: review follow-ups on the undo commands ([`e66cd3d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e66cd3db0d04a05184b40999d437bb0620749614))

### Docs

- **messages**: point phase-navigation handlers at the controller ([`d83d93b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d83d93b07a7bb8970eae2eabcf5adedf14545686))

### Test

- **device-viewer**: cover the message controller ([`3893ce3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3893ce33eeadb985698f9125523db1f501b1e79a))
- **device-viewer**: mirror the pane's recorder in the undo test ([`2161b16`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2161b169e5e18d3a29ce9e2449cc5af86ee5e2af))

### Chore

- **device-viewer**: ruff-clean test_protocol_tree_display_state_handler.py ([`5e1ad1e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5e1ad1e34068581998e239ce4fbff9b367a476f0))

## [v1.25.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.25.0) (2026-09-29)

### Feat

- **image-viewer**: add a perspective-correction demo ([`0a76053`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0a76053b6f5bea66e2ec4449f58e035654d7874c))
- **image-viewer**: move the image viewer into core ([`22cf5d6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/22cf5d689aebf2a286ebf23cb5e0463695996171))
- **style**: add an open-in-new icon ligature ([`87de578`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/87de5780e469bfa90d41f6ee6ae95ba6697a58a6))

### Fix

- **image-viewer**: use the Rotate Device glyph for rotation ([`d6d40b7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d6d40b739477a77da83b67b790f57349c27d19e5))

### Refactor

- **image-viewer**: device-viewer icons in perspective window ([`8a6fcd8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8a6fcd80398e7694f2e994967a48c05e7dbd2270))
- **image-viewer**: icon toolbar in the perspective window ([`ded89d7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ded89d72d4e280a212d27120912d20aa89487702))

### Test

- **image-viewer**: update tests for the moved viewer's API ([`67968e2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/67968e2373660df6ec7e6c7859e45591f4050088))

## [v1.24.2](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.24.2) (2026-09-25)

### Fix

- **portable-dropbot-controller**: log fluorescence filter moves ([`370fb31`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/370fb3117ce13459be4b4f754a2182f5cb0da29c))
- **device-viewer**: stop logging the whole media-captures list ([`af4c3ca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af4c3ca6c89fc1ff07ded66634446242e9e5da8f))
- **portable-status-and-controls**: fit exposure slider to its cell ([`f57fd67`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f57fd6731d935d0d11b690203801fd682345d7e2))
- **portable-status-and-controls**: follow the wheel, not a stale pick ([`76f5920`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/76f5920aa88d648f38a71bdc64e9886d35640df3))
- **portable-dropbot-controller**: report the wheel's actual filter position ([`cb6846a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cb6846a31248ee4f215a7742aaa623d60484e1f1))
- **portable-status-and-controls**: follow a re-selected step in capture panes ([`653392f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/653392f1314de6c218d25f30558e7e22188a1fc3))

### Test

- **portable-dropbot**: cover the manual filter pick following the wheel ([`3fbb59a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3fbb59a493acf48c1d98e5766b225f10e55e8460))

## [v1.24.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.24.1) (2026-09-25)

### Fix

- **protocol-tree**: restore demo window's run-control wiring ([`246f4ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/246f4ac5197763f60da65fddd7060292cf1f49a2))
- **microdrop_utils**: drop the end step only after a forced end placement ([`c6bf5cd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c6bf5cd1ac12613b473c8a889f71c260d444200d))
- **device-viewer**: pass the full polygon list to the neighbour sort ([`6eedcb8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6eedcb8e5e033105d9ba9e4142aed96fc79fc4bc))
- **microdrop_utils**: sort_polygon_indices_along_line never sorted ([`c7dd77d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c7dd77df0ab8705d97582a9462ef00a0016c3236))
- **microdrop_utils**: guard zero per-phase duration in idle-phase calc ([`933dfc2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/933dfc2a54951d21b5a980cb0c3c6f777f56a338))
- **plugin_management**: guard purge_plugin_modules against empty dist_name ([`a3e628a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3e628ac89500fd918035f33464a038a796cd908))
- **portable-status-and-controls**: clear step ticks on detach to manual ([`3bb94ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3bb94efbd78bde6cc3ef6b04a99b930881108951))
- **protocol_tree**: status callers pass the slug shape ([`6fa6ea0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6fa6ea05b3b861324e5e2a1084a055c01170b825))
- **microdrop_utils**: measure a wide loop's rep in slug phases ([`811bc95`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/811bc9567cd7adce21c569e93d32509e79a2e494))
- **device-viewer**: reject unknown fields in camera-control requests ([`497b55f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/497b55fad8f9e552c8cbfb213c8454bde556aee3))
- **device-viewer**: validate camera-control requests before applying ([`e32a1d6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e32a1d64492d4440b7d050cf7f6886b47df0db4f))

### Refactor

- **app**: drop the dead sidebar that imported the tools menu ([`02c9067`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/02c9067c10024c54b6586c86df74e02f07f1124f))
- **dropbot-tools-menu**: own the self-test dialogs ([`54881bc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54881bc9e391696dd7b0ba51af3983b60131ef4c))
- **dropbot-controller**: re-export topic schemas from consts ([`de3929f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/de3929f289135bd106a83f99b24883db0e9b7f83))
- **protocol-tree**: import device-viewer schemas from its consts ([`693bf2b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/693bf2b2d2b52787874d0c400dbb2495ae1c87fc))

### Docs

- **readme**: mark MicroDrop beta and show the tests badge ([`83533f8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/83533f8c73126c463545d37d54c10199b545dd6a))

### CI

- **tests**: make the pytest step fail on a failing test ([`55b05e6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55b05e6cabfd36a3750546e6086d2823da9bf365))
- **tests**: add libpulse for QtMultimedia test modules ([`6a13270`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6a132703440ee686abec9464cb2921480b493515))
- **tests**: install the Qt runtime libraries before pytest ([`cef3920`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cef39200e13b42e1c41c8a00f7484ed19437e9f6))

### Test

- **protocol-tree**: drop the demo window's status-poll tests ([`1bde19b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1bde19b604c725269940908337bcc25aa4a0a058))
- **protocol-tree**: expect the tab separator in the tracker's name ([`92fc693`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/92fc693b6465b59dfd7b5c0892965cc49515bbfd))
- **protocol-tree**: stop test_logging_reporting from hitting real Redis ([`1a0d1de`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1a0d1de44ef797e7741d654c600aa6edc7be665c))
- **protocol-tree**: retarget pane tests to the dock pane (#663) ([`e161f67`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e161f67a1783ad4044082293fecad36785fc4cc8))
- **protocol-tree**: retarget trail-overlay clamp test to dock pane ([`a5638c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a5638c17764fe3972dc1780e5a1af2eee5b7b208))
- **protocol-tree**: retarget base-demo-window tests to fixed API ([`6efc0c5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6efc0c5f3d6a6db65adb0af7ab88b140d07dc1c4))
- **protocol-tree**: fix executor signal/parallel-fanout tests ([`d26849c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d26849c0409604470dd403702e8e4fad3f1b81ff))
- **wide_path_demo**: phase heads follow the end-of-route drop ([`d7e622c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d7e622c388460bf6942709861a21a4846b548986))
- **microdrop_utils**: re-derive slug answers from the board audit ([`5424f81`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5424f819e885cc93788d576c63b471656e691069))
- **device_viewer**: add dirty_device.svg fixture, force past .gitignore ([`014e623`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/014e6234470fcb1a67a2c398ef331d3b18a814d2))
- **device_viewer**: fix svg_electrode_layer fixture and assertion ([`62afbfb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/62afbfbb63a6a66f3794ce0c20ca1306ad9173c4))
- **device_viewer**: fix stale Electrode path shape, drop dead state test ([`abeaced`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/abeaced38a426aac29bf6d26ceeb98a4f0547efe))
- **device_viewer**: update route params for post-#682 shape fields ([`97af22f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/97af22f87056fc690990ede928a715ec8fc433dd))
- **device_viewer**: fix stale publish_message.send mock convention ([`3051de9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3051de97a30027ed0f9cb1d40016bbf8520404a7))
- **protocol-tree**: update electrodes/routes column tests for #477/#682 ([`c5cdec7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c5cdec723be97afb9e481f5f5855e1101c7e4d3e))
- **protocol-tree**: instantiate publishers to read validator_class ([`5734a8f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5734a8f0544dd3d5378c70ee4754719baa730d49))
- **protocol-tree**: drive _on_step_started with a traits change event ([`70918b4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/70918b4784bc5e54ac53f674399e015531332014))
- **protocol-tree**: expect recentre in slug_shape_for_row output ([`65404a1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/65404a16dc204df9f5adacc154ccd8266e46a745))
- **examples**: skip the remote rsync test without a live SSH host ([`38c517d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/38c517d8f26d0678cc5833849fe505fa0dc1c13b))
- **examples**: read validator_class off an instance, not the class ([`60ec4ea`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/60ec4ea9823c6fdf31b1bed199f4c32e152ec924))
- **plugin_management**: isolate installed_plugins() test from real env ([`51ee5cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/51ee5cf6344a0d6d7afd5857ba9b2f2d0c8082d0))
- **volume_threshold_protocol_controls**: isolate guard tests from Redis ([`d7b3652`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d7b36520e7e54b06b5c49c3a23a3e3c54a93ac4d))
- **video_protocol_controls**: use dotted_path() for record step_id ([`f53fc4a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f53fc4ab17be51cf4079c8e349caf50564027bc3))
- **video_protocol_controls**: update tests for the capture compound ([`e496ad5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e496ad50264810e9b44b7d15138ba107d3e26c9b))
- **dropbot_protocol_controls**: patch the renamed calibration lookup ([`817bfec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/817bfec800a8b98e1ae51b1236b4a5ad5de782a1))
- **dropbot_protocol_controls**: update droplet-check tests for default-off ([`f71af96`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f71af96613daf21281ccab80d7e1eec299447ff3))
- **portable-status-and-controls**: match frame_label's stamped format ([`ed451c7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ed451c78b19cb291c3a094e42b425f7c37cff068))
- **portable-status-and-controls**: patch the shared base in capture-pane tests ([`395ec88`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/395ec88265b8d0095b91657c386913d85b2d5990))
- **portable-protocol-controls**: give capture-column test rows the sibling column ([`e0449a5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e0449a59e4e71843d550f96c995d997940e47571))
- **device-viewer**: expect the defaulted hold_auto_exposure field ([`ec33267`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ec332671fc0f4db6965a616fdd61cec31168712c))

### Chore

- **protocol-tree**: ruff-clean test_protocol_tree_pane.py ([`e8f8ded`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8f8deddc81457778395fee6e7c644812c4172ea))
- **protocol-tree**: ruff-clean test_hidden_columns.py ([`2065cb9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2065cb910f22715746c2f98d284da5310ba876d1))
- **protocol-tree**: ruff-clean pane/demo-window files ([`6aec07d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6aec07d2f330d9b8ca72802b248e1dbeaede288b))
- **protocol-tree**: ruff-clean test_executor.py ([`6557de0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6557de0e80174ae76ccac13254a33b436f3b9730))

## [v1.24.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.24.0) (2026-09-24)

### Feat

- **utils**: say how to start Redis when the workers cannot reach it ([`4418a2d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4418a2daa394e0a44a22c66f66c91dd35117595b))
- **device-viewer**: undo, redo and revert-all in Edit Connections ([`4a12fa3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4a12fa38abdc8101613f1b72b43ff57a9ccf5f12))
- **portable-ui**: park motor option, icon homes, filter dye names ([`70011b6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/70011b6fc6175681b7071e9317da5687ea1e0423))
- **portable-ui**: move the PMT to any spot and home in place ([`1fb2d43`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1fb2d436cbf9a9bc37b6c9f338e9f709ebb28e52))
- **portable**: make PMT and fluorescence capture exclusive per step ([`9174c9e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9174c9e5aef96d090a0b86675c0cb59dd51c2563))
- **microdrop_utils**: nearest-centre top-up, trim wrapped phases ([`6484f26`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6484f26e259b4a69f058758001a5fc144cefe2fb))
- **device_viewer**: lane sliders, width cap, route preview layers ([`3ec72da`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3ec72da28da7ac8928a583699ff7023b5276daa4))
- **protocol_tree**: carry recentre, play locked trails as slugs ([`d6b909c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d6b909c294d962f1fc0bd573def4106ca6888ce7))
- **microdrop_utils**: slug rules from the board audit ([`2139af4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2139af4ee2076e152a7d641be717b35c49940546))
- **device_viewer**: live slug preview and a tidier route sidebar ([`35488c7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/35488c77cabc924a3ee777bbc062bf011be28464))
- **protocol_tree**: protocol runs play the slug shape ([`cd6d716`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cd6d716294e23aa6ba6e548244d79a1d1a0382a9))
- **routes**: the slug shape as step parameters ([`8aca1bf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8aca1bfb69879a7f771f9488b3c54e5154dda923))
- **microdrop_utils**: slug shape in the execution plan builder ([`a84f966`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a84f96625155de3c64b4087edff057061585a90f))
- **microdrop_utils**: wide path geometry and notation ([`914e71b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/914e71b2e751784e9b086eabffa119a574aaf483))
- **portable-ui**: auto exposure per filter and held on untick ([`9a43166`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9a43166ac0d0ae8695f0a7047420c24f70fbf095))
- **device-viewer**: report and hold the auto exposure value ([`3653bc4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3653bc4d976eb995859afe002926df719e54ca4c))
- **portable-ui**: add manual fluorescence controls ([`c4519e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c4519e1276dc29c371c8d85b0528cb064c516d8a))
- **portable-ui**: share one capture-pane base for PMT and fluorescence ([`ad202fd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ad202fd72b34666fab9b13d5c49410a6843abdfa))
- **portable-ui**: show the filter per fluorescence result ([`ada0327`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ada0327b810083a442117ff2d584aa0279522003))
- **portable-ui**: collapsible, resizable fluorescence results table ([`a7acc7d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a7acc7dd20b111ac4c8a68afc4cdd1a3f18ba5ac))
- **portable-ui**: stepped slider for the fluorescence focus cell ([`c80cbf3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c80cbf37c513128fa1bb4dd75dc47d84d1e1191b))
- **device-viewer**: set manual focus over v4l2 when Qt cannot ([`30b67e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/30b67e1e1a85be491b6d6d9ef4e8336e23d4d85a))
- **portable**: fluorescence capture protocol column ([`b108361`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b108361d1a0a2dcd0b7fd86ea9d9c7f99aacb9ef))
- **portable**: fluorescence step-capture value contract ([`40ee926`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/40ee92600b205ee8d1ae988da73aa6605c5fa8b0))
- **portable-ui**: Fluorescence Capture dock pane ([`fc6748d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fc6748df9cc145b5e4930e8f8242c4466bc470a6))
- **portable-ui**: Fluorescence Capture pane model ([`b396d59`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b396d599240752067111af375c031bb50ecaaafb))
- **portable**: fluorescence capture routine ([`48d3d9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/48d3d9b553a34eb9d86d914a63e1e65d65ff5c90))
- **portable**: dispatch subscribed signals to on_<x>_signal ([`348cf62`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/348cf62cbbc77ff53b4a4748651be0b34df9fe9e))
- **portable**: reply bookkeeping for the fluorescence capture ([`4c987c5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/4c987c5d03329199707adba7f4eb5c2fda59bfd6))
- **portable**: fluorescence capture contracts and topics ([`80c78b3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/80c78b3a961677143003d266ab60bdde3de06da0))
- **device-viewer**: apply exposure and focus requests on the camera ([`f9ef052`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9ef05242ea89705cba3b9fe83a0a941cee58783))
- **device-viewer**: tag captures with the requester's id ([`2a9dcea`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2a9dcea83db95f7050ea7c2f5e385042740733d1))
- **device-viewer**: camera controls topic and applied signal ([`dc89cb4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dc89cb4d320253fb9872a3b355b89415aa6facbf))

### Fix

- **device-viewer**: publish phase-nav mode only on a real toggle ([`03dd173`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/03dd173f8605bc00106a01dba6b414c890a66e1d))
- **protocol-tree**: skip experiment change before the pane mounts ([`8d83872`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8d83872fe70a445554ab8de20d5bc0def67d92b4))
- **protocol-tree**: declare listeners at plugin start ([`067a5b3`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/067a5b3a8275aa67de4c89f676eaae6faac759c1))
- **portable-controls**: stop routing to the disabled calibration pane ([`c590da5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c590da5cfda067d57ded374feb3684d86a228610))
- **message-router**: drop session queue on stop ([`e881483`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e881483058fd54b59b4ced034f6ba0dda692c1a1))
- **utils**: keep the Redis warning tool-agnostic ([`6061301`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/606130172dac7056e24946fd4d0fb73fccc776c4))
- **utils**: let a failed worker start surface its own error ([`d82d53f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d82d53fe1bc18e983b8be5e47128631738c56bf0))
- **portable-ui**: show the filter's dye name alone ([`0106277`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0106277731ef8010691fecd9475b97655203e22e))
- **portable-ui**: name the park checkboxes and spin the LED % cell ([`04756c1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/04756c10eca448fb34a843508b5edb8f44aadb73))
- **device_viewer**: widen the alpha spinner column ([`84f9c98`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/84f9c98080835a4f269f2dd51a956c55e4d61a01))
- **device_viewer**: phase nav electrodes and param echo ([`43b5505`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/43b55056052f7e4c733c53648c4354d6151adb02))
- **device_viewer**: keep the Phases toggle in reach, align the lanes ([`3b22a91`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3b22a91f1bf0c8d1d3832635e10b523f5fdecdf4))
- **device_viewer**: stay on the last phase after a sidebar run ([`02f289b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/02f289bc244923ec41b04cdf5bd0d8fd9d6e5078))
- **protocol_tree**: one column per id, tracker survives duplicates ([`3b387cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3b387cff4e6c1e8fe6e6e9bb7fcf66e0eae261c3))
- **device_viewer**: keep phases and free-mode params in step ([`43e0851`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/43e0851a7458b80d6af98bd159cfadf390fe4bce))
- **device-viewer**: stop reporting a stale auto exposure value ([`c54f3b6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c54f3b63e19312f2fa9bfd06b2795363d312eb9a))
- **portable**: cap fluorescence exposure at the camera's 200 ms ([`b5f502e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b5f502e8a374507cbef211dc89f14d744273f4ee))
- **ui-helpers**: never let a slider range change clamp its value ([`a3f440a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3f440a33b9796e87a25ad4a902d64e006ed379e))
- **device-viewer**: switch auto exposure over v4l2 when Qt cannot ([`85ff874`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/85ff874f12813ae891d0bbac09134c3ec34786b8))
- **portable-ui**: fit capture row tables to their rows ([`ccc2954`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ccc2954029ccf41f6213b3fdd7e011ce4350fef7))
- **portable-ui**: stretch the fluorescence results File column ([`f9a57bd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9a57bdbfb42a0d16450e64b9107a273cb23d16b))
- **portable**: number the filter wheel positions 1-5 ([`bc2938e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc2938e3abe0bb949223b7b0920a0de7dfe1fbd6))
- **app**: never let a layout pyface cannot save block exit ([`423504a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/423504a553e387881f9211b1987e3d1e8f5f8079))
- **portable-ui**: grey out fluorescence Start while a protocol runs ([`8b7da6f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8b7da6f57b0bbdf1eb59e738ab24b3cf0bcfc8e3))
- **portable**: never let a failed done publish escape the capture thread ([`1a8ef39`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1a8ef3983a1508c713941aab0131728d0882a793))
- **portable**: accept an echoed 0 as a successful LED set ([`576b36d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/576b36de823697440c8a71ccec89f132054ef06b))
- **portable**: report a mid-move disconnect as an aborted capture ([`38d4df8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/38d4df815a8f7d4156c1c033a9b71cec86ee7395))
- **protocol-tree**: list each media capture once in the report ([`378f255`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/378f2553f3168d1ca4259e4841db2e3025bf3ce1))
- **portable**: move the filter wheel through the generated proxy ([`ba538b1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ba538b1c4ad3763098e74aa15a3f783513fac7b8))

### Refactor

- publish advanced mode as an app-global key ([`c200cbf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c200cbfc654c3cecbd0f9a675312042a789ba8e7))
- declare app-global key names in each plugin's consts ([`ab35ff4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ab35ff400396985f4bd0a4d8655d04ef0e40a8a2))
- rename the capture/recording show_dialog key ([`2769044`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2769044c4ad8b857683bd92ba35a6059d6d853b9))
- **protocol-controls**: share one step-capture codec ([`3b3a0b7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3b3a0b72ae70fed218f6f18959093aa159caa612))
- **portable-ui**: drop fluorescence focus and manual LED controls ([`70825e1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/70825e129d4b7d97dc1c1405ce7ffa4cd335d46f))

### Docs

- **messages**: the slug shape keys and the geometry lattice fields ([`2ef00bc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2ef00bcf1d978d37f820b7f4d11bda7b37de2daa))
- **protocol-tree**: correct the media-captured parity note ([`a2f3e26`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a2f3e268a756a971c118d0ef2567b5f4c359caf2))
- fluorescence capture topic map and traced flow ([`2ae446e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2ae446e09e5af192313875064a885b631bce2d37))

### Chore

- **lint**: ruff-clean the four files the advanced-mode key touches ([`ce61d63`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ce61d631af138b71ffa4cd7ed999bb219064eccb))
- **lint**: ruff-clean the controllers the app-global keys touch ([`81ac09a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/81ac09a8c862d87db8b4f6a360474b615c6fdeb3))
- **lint**: ruff-clean the video capture/record columns and tests ([`33595bb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/33595bb75c4ce0ea145699fe22301307d304a19a))
- **lint**: make every package dir visible to the import contract ([`b934895`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b9348953aa3e1c504355ced2940d212d1ab01dd4))
- **lint**: ruff-clean broker_server_helpers ([`f5dbb47`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f5dbb47c3ceb0c4e7b619ff16f79bd415370e32e))
- **env**: sync environment.yml with the pixi manifest ([`1c569cd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1c569cd7c2f81e19b2041081c6a8a62845b41870))
- **lint**: format the alpha table view ([`5564620`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/55646202da73efde91ba0430dc1e6382a61d5a26))
- **lint**: ruff-clean the electrode view base ([`28b863a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/28b863a8cd66353ae464cb483b86f3730913151e))
- **lint**: ruff-clean the phase-math callers the slug shape touches ([`f99b9b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f99b9b0c2f0836bec0305faa0e1aec25fefb7ce1))
- **lint**: ruff-clean the four files the slug shape touches ([`537b1fc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/537b1fcdcc7b4ccf23c51c1064443607f30d3001))
- **microdrop_utils**: ruff-clean route_execution ([`caca54a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/caca54a80cb8e5e527bfa9d5c9c218d0cac4c21a))

## [v1.23.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.23.0) (2026-09-18)

### Feat

- **portable-ui**: pick the PMT exposure slider's range ([`753cc96`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/753cc96270ca028995e303db88c5fd0c915b04e5))
- **portable**: PMT step captures in the protocol report ([`e1ab929`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e1ab929e3aa04afd36e3a474e0d8bb5402f47baa))
- **portable-ui**: spin box for the PMT exposure cell ([`7bbec41`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7bbec41609d12bc113359c05df98de20bc9367ac))
- **portable-ui**: PMT Capture pane follows the selected step ([`7a410ee`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7a410eeddbc56515e9df831105c474ac2e4382ba))
- **portable**: PMT capture protocol column ([`9b0a873`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9b0a8738fb67a7bb655e159c1c970abe7aaae287))
- **portable**: protocol step captures in the PMT routine ([`a68c32c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a68c32cc8eac5982a469c83448119e06c150a009))
- **portable**: PMT step capture contracts ([`6d88337`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6d8833709024f480e8c77aa763d3ec5ed14bf3e4))
- **portable-ui**: PMT run history, file links and countdown ([`f714b00`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f714b00a9adf894743c014b45582e55b2e3cf85f))
- **portable**: exposure time in PMT capture progress ([`2c03862`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2c03862a687b354a442979d6cb62ff7f74889869))
- **utils**: link and active-row highlight table columns ([`95a9160`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/95a91607416511fc04747211ed351299424ab0ff))
- **utils**: reset-view button on the live plot editor ([`af331a7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af331a75879b727da85a442da9e74f1d1ee73f25))
- **portable-ui**: PMT live view, results and acquire ([`ae9209c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ae9209c0a566618ba239526324118283c04fd4d3))
- **utils**: live pyqtgraph plot TraitsUI editor ([`069a7ca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/069a7cac9202759bc8a48360d5c3dcfd0d56dd1f))
- **portable**: PMT live stream, ADC query and acquire CSV ([`b95c87b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b95c87bde01854b8a7bc2318b58aa14a6bbe42a0))
- **portable**: PMT stream, ADC and acquire contracts ([`e8e8440`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e8e8440fbebcfe1906dd951c22a2d21a7c3dec66))
- **portable-ui**: PMT Capture dock pane ([`59dbf4a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/59dbf4a1053785fd80d4f43fc73fb2f1b473726a))
- **portable-ui**: PMT capture controller and handler ([`72407bb`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/72407bbcafe79e194b52e762cdafda1cb53bb1f5))
- **portable-ui**: PMT capture pane model ([`c6616ad`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c6616ad4fa0df1328b3b3a842e8bd7f5faef407c))
- **portable**: PMT spot table and capture routine ([`2f7e132`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2f7e132d63b9a86634572e7076627d1d91b84bde))
- **portable**: pure PMT capture helpers ([`8ad83e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8ad83e85495a374589499b8df473aef9bf91351b))
- **portable**: PMT capture topics and contracts ([`e87cfe9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e87cfe9c9a41fb94ce3fad6ce07a9fff4e1cde48))

### Fix

- **portable**: drive the lamps through the generated proxy ([`a87f56a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a87f56ac9239493acc58b0f0d3434836697048c3))
- **portable-ui**: full-width PMT spot table and live plot ([`68d686c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/68d686cc9b964c743cb45e4aa69e62cda2f8c262))
- **portable-ui**: PMT results table as a plain list ([`69a289a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/69a289aeb512cd37375a5abc9670182017694696))
- **status-panes**: destroy the pane control before its editors ([`395690e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/395690e9d70566381daefb334c7e978538c646f5))
- **portable-ui**: stepped exposure slider in the step table ([`821bb5d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/821bb5d8c457e1c6b45ae51c0c7585342f4289fb))
- **portable-ui**: step the PMT exposure slider by 0.1 s ([`09e0f73`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/09e0f73698540e511021c3216903178088b7758d))
- **utils**: one editor on the glyph checkbox column ([`20ba51a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/20ba51a702c199a4e5da1a79a3a40b9aee6d9dbe))
- **portable-ui**: tick the PMT exposure countdown ([`91e74bd`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/91e74bd116ef1f2b0afb6380fd4de03513798e41))
- **portable-ui**: size the PMT spot table and live plot ([`1adcdf0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1adcdf087cad80b56df29a4b6e26583a5ee94f79))
- **utils**: keep the live plot a fixed height ([`deb2369`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/deb23691009acf385c02f4b322925d18e92ad960))
- **portable-ui**: give the PMT tables room for every spot ([`0703ecc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0703ecc906a59fe3643de558621633251080dbe9))
- **portable**: number PMT spots past the park location ([`e1f0140`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e1f014019f279b4de2563419e6f57a92f5a6f0b2))
- **portable-ui**: hide the calibration dock pane ([`bc60330`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bc6033099dd19b307ea74d72e4eee21620e69558))
- **portable-ui**: keep the last PMT results path on refusal ([`c68c27f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c68c27ffc5163b4338c7cc797c11b31fe6399e33))
- **portable**: sane PMT exposure default and bounds ([`5495989`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5495989340db3ed561653dc36d99f9dab029697b))
- **portable**: run the PMT capture off the actor thread ([`0f76506`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0f76506d64dc8314422ef004566bb25d9fe3b69a))
- **portable-ui**: describe PMT row's editable traits ([`15aa9b1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/15aa9b147ff281df0c23b9a00dbf02e0b8dc87eb))
- **portable**: harden PMT capture teardown and its checks ([`0bf9ff2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0bf9ff213613cb0e2fb6396699a59096051e29df))

### Refactor

- **portable-ui**: drop the acquire from More Controls ([`898b475`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/898b4752fabc6e2d793d2bf16d8ba69c1ec25d06))
- **portable**: take the PMT stream command id from the driver ([`03b6c77`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/03b6c77d1061c276fc24a05b65980820a780c6b5))
- **portable**: use the dropbot-portable package driver ([`6c8732b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6c8732b94f527f0fb7952a5a33d465e2aba407af))
- **portable**: keep PMT consts free of the driver import ([`5643c71`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5643c71f423671c38f00b6643e24bc9ca0c76b81))
- **portable**: hold the board proxies on the session ([`d21af79`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d21af79ba8976259d96fbc1a8cb834d71813a155))

### Perf

- **examples**: lazy-load the portable backend plugin ([`b0ffe89`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b0ffe89abfde7c3128ff4343a7d488e7671c147d))

### Docs

- **portable**: design the PMT protocol column ([`148db85`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/148db85eb40872edd158d7e8cd44e32add572eb0))
- **portable**: scope the package-root import rule ([`3435ef9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3435ef9dc5dd9961cf4b27c42d821d22923bafb8))
- **portable**: PMT capture runs on a thread ([`901d14f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/901d14f43a3bc2849f44af8fccfe3ef6f9f639e6))
- **messages**: portable PMT capture flow ([`69cf618`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/69cf618293d2a2989227bfab295991ec5fdafd94))
- **portable**: design spec for the PMT capture pane (#601 increment 1) ([`8acab00`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8acab00250d9857431133876c1c6c23d66da0001))

### Test

- **portable-ui**: respect the new PMT exposure minimum ([`0423803`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/04238031a1982757d7c6de0502e434f0e7eac03b))

### Chore

- **portable**: let the import stamper label the vendored driver ([`7002ca4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7002ca4ac70c9ad5ce0a548be074977c847c0d6f))
- **portable**: re-vendor the driver from python-driver main ([`88d4107`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/88d41075d8fd4444f4fb42cbda4b9e8e2671b8d7))

## [v1.22.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.22.0) (2026-09-17)

### Feat

- **device_viewer**: add Edit Connections dialog ([`53cf1b0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/53cf1b06162735e8e301537092a81ba087256f6d))
- **device_viewer**: redraw main view on connections change ([`8da5552`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8da555283fe5edc67b1cdd8a07fd0ba97f6ae3d7))
- **device_viewer**: edit connections on the SVG model ([`2eecb5b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2eecb5bdf496af893adad37d799c924d59b80769))

### Refactor

- **device_viewer**: share nearest-point snapping ([`7df9f11`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7df9f1187265c3e31d6c613cac88873637594553))

## [v1.21.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.21.0) (2026-09-17)

### Feat

- **examples**: add cli() entry point to the runner ([`90a2418`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/90a2418e83b03faf324fa37f8679eca649532455))

### Docs

- consolidate project instructions into AGENTS.md ([`eef4b28`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eef4b2826ce91b127fd5b3d26f2d4fee57921165))
- **agents**: spell out the blank-line rules for function bodies ([`07416ba`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/07416ba59e780c261f26b54df7715af7ecc9e8a3))

### Chore

- keep superpowers specs and plans local ([`856f6ec`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/856f6ec6102377eec51c09c436c29ce210fa0534))

## [v1.20.2](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.20.2) (2026-09-08)

### Refactor

- **legacy-import**: use pathlib instead of os.path ([`af2140c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/af2140c3436d60ef91b474066be03a363c8d68ab))

### Test

- **legacy-import**: pin scanner and dialog path handling ([`a557432`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a557432c6be7084d9c383cc53f11658d4d163e63))

### Chore

- **legacy-import**: bring the two modules ruff-clean ([`9443a35`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/9443a35563359c4a70ccee898a1493b53ed518a9))

## [v1.20.1](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.20.1) (2026-09-08)

### Fix

- remove redundant super call. traits init does not need this. ([`beb0e29`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/beb0e2949b8bcff2b56861f05106553de3bacd43))
- **status**: persist voltage and frequency via the range helper ([`2579ee7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2579ee739166ecc49fea41aad074f8ccc25c9596))
- **status**: start from the persisted voltage and frequency ([`16e0b11`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/16e0b119287078a12c9a62d175c3290b90854847))

### Chore

- **manual-controls**: import the range helper via consts ([`a43fe74`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a43fe742155bb49854c488f3bdb299f92d79b09b))

## [v1.20.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.20.0) (2026-09-04)

### Feat

- **dropbot**: link raw data JSON from the self-test report ([`106c804`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/106c804048dabcdd061d76e5b60ac417d2bf2e4f))
- **tools-menu**: link the raw data JSON under the plot ([`3df0c50`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3df0c50713efc9839519e86a88a6aa2984d62eb5))
- **tools-menu**: interactive self-test result plots ([`db374be`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/db374bea5f68c68414bc0924c1e55e0286615224))

### Fix

- **dropbot**: log where self-test results are saved ([`837dc59`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/837dc5986706bce1c9570a5d9b5129a6a7b83a6e))
- **utils**: log missing reflective handlers at debug ([`e4e0cb5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e4e0cb5f30e92c2ecddc607cad6b9cf7c58f3f1d))
- **opendrop**: import OPENDROP_IMAGE from the right module ([`854084d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/854084dd1059171768b06f050c78a0905f27eb7e))
- **device_viewer**: guard screen recording JSON parse ([`fef91d8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fef91d873c918c5a65b6f95599caba1e2a3d3c78))

### Refactor

- **status**: stop importing the preferences model ([`90bed98`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/90bed9801afc846acff0773af7c97b23bb5e4a1b))
- **utils**: move force_for_step to microdrop_utils ([`965bd89`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/965bd8962c4115d25c133e914c8efbcb5ab14f07))
- **dropbot**: publish raw self-test results ([`d84e63a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d84e63a96daccf79f6fdee4004387564e7924913))
- **tools-menu**: show self-test results from the topic ([`6413d37`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6413d3761c552df460a1394b12a36be73ecec294))
- **dropbot**: publish self-test results as a topic ([`ef8d6d7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ef8d6d7d888e9eecbb350764e6198a1126b66160))
- **device_viewer**: rename _show_media_capture_dialog ([`c142281`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c14228175422b0d2d19d3e8df4e42193e20d079f))

### Docs

- **agents**: say where lint-imports must run ([`a6073a5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a6073a5aa6a26af814485b4dcbd938fa7032e5e4))
- convention rollout design spec ([`0eb9c87`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0eb9c8731816358551e72e609e26c63cb43df5e5))
- **agents**: note the unit-test partition runs in CI ([`7ef9d0f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7ef9d0fcc032dd166e2a745edbac411977308ca8))
- **agents**: name the launcher's lint task correctly ([`b677f0b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b677f0bac343a8e75882a59ea123cb542136ff05))
- **agents**: document import-linter enforcement ([`86f4d6c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/86f4d6c0da429e540416cd50e3429dcd7ae48723))
- **agents**: note the import-section stamper hook ([`931b22a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/931b22acc81648ad0cebea221854663fa152d234))

### CI

- run the import-linter contract as its own check ([`a0f4867`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a0f4867be50f3e5cb6a1f191a3fb39d0dab2d7d9))
- gate PRs on the import-linter contract ([`c854c9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c854c9bda044ca175b3460e2331c09a515d77787))
- run the unit-test job on ubuntu-latest ([`8f3b936`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8f3b936aaacc47923552848a235272909e277dec))
- run the pure-unit pytest partition on PRs ([`1921478`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1921478b2b2c3bdcbca378cb635a961f50e42b64))

### Style

- **utils**: bring dramatiq_controller_base ruff-clean ([`6334b1a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6334b1abac6393c5cdd0cb4cc82156e7a1c7b626))
- **device_viewer**: label import sections in dock pane ([`835aa98`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/835aa985eaf9b70beb5c6abe46fc2e988404354d))

### Chore

- **pre-commit**: consume microdrop-dev-hooks, drop tools/ ([`ff82a61`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ff82a611d93246909323d2a94e4e61413113f8b0))
- **lint**: drop import-linter debt fixed by #657 and #658 ([`749fd81`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/749fd81ccc98c571e7f13fcae31da790500a558d))
- **lint**: enforce plugin decoupling with import-linter ([`6725d0e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/6725d0e59db22e3edf8ce37a8936633d2b0cf95c))
- **tooling**: stamp import-section headers in pre-commit ([`c3b9c81`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c3b9c810bd44df14b0b5fedbff3a46227011ec90))
- **camera-control**: bring camera control view ruff-clean ([`b270ba7`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b270ba751690173f31ddf54e87b5819dc45a0e69))

## [v1.19.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.19.0) (2026-09-03)

### Feat

- **device-viewer**: enable Merge only when a merge can succeed ([`27268f8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/27268f897fc498c5124b41fd326ca3fdc23ba5a8))
- **device-viewer**: default zones tree height 250 ([`a416325`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a4163258946a750fdc035910a3871517df6bd306))
- **device-viewer**: zones sidebar tree-table ([`07fa457`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/07fa457f77d5f381e33ccba5931649ed99f8a0ee))
- **device-viewer**: zone ordering, multi-select and undraw ([`32d0799`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/32d0799b371371b49ce431d655ffa1e23ca8c27c))
- **device-viewer**: layer zones by sidebar order ([`7759036`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/7759036e8e99c9e7c5e66456bad1bc913a9abd2a))
- **device-viewer**: zone table height preferences ([`26b325b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/26b325bb28e2511b31be76d2bfa937a954f54f94))
- **utils**: ToggleButtonEditor and a styled color picker ([`a73c5ef`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a73c5efe049bcb2df749bd14a9d37619ac3d0ee6))
- **device-viewer**: zones sidebar table buttons ([`23aee9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/23aee9b6329b93b8235464518eb966586e7d4ff9))
- **device-viewer**: zone rows delete themselves and self-name ([`5ec49d5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5ec49d5da4b2bae1625f9a3af438e3fbac456670))
- **device-viewer**: zone tool buttons like the Paths picker ([`0708c11`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0708c117ee59027f98eb759e8493e5731ca3ed88))
- **device-viewer**: warn when zone regions fail to load ([`50224ca`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/50224ca51c42d6e7bf3e4bd691b334b71909ce15))
- **device-viewer**: zone undo/redo on the app stack ([`b19f369`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b19f3691fdc9ace9342860d5fa7b86725d94c6a6))
- **device-viewer**: drag zone regions to move them ([`54f3302`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/54f330295a47c4cf31cf2546c85c6d61d7cbe2fc))
- **device-viewer**: floating zone action strips ([`528c375`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/528c37531b26970d0733b628b704024288f1a56f))
- **device-viewer**: zone draw and select interaction ([`a01d580`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a01d580b5fc73cbdc1784a44b05a35921885f169))
- **device-viewer**: zones sidebar section and controller ([`dc5b168`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/dc5b1683e66fd8d48f0c1a8cc690678c8af8ffd9))
- **device-viewer**: draw zone regions as an alpha layer ([`15582f4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/15582f45da2d857e9f3bc9211b0abf0d828b8a62))
- **device-viewer**: mount the zone manager on the model ([`d827f0e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d827f0eea09d760841611e2a96372d78fb7c3ca4))
- **device-viewer**: persist zone regions in the SVG ([`d2c0be9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d2c0be97e3e52d31908cf833c8971ef2be0b47a5))
- **device-viewer**: Qt-free zone layer manager model ([`81b10e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/81b10e86e7aafb6e03602e82a120ce8b5480de52))
- **device-viewer**: zone constants, alpha row, prefs mirrors ([`63f7945`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/63f7945a60c06441fb6b312ea4914bbe2fb7a6c8))
- **examples**: standalone electrode zones demo ([`bd9146a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bd9146a009fce468657e6e9b460fe8710eba6593))

### Fix

- **device-viewer**: report rejected zone moves on the status bar ([`e45914d`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/e45914d760693a7c551e570641b159fe7755b38f))
- **device-viewer**: keep folded zones folded across tree resets ([`1edfd63`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/1edfd63fac14edeab857dd485a858ff19e5cd77b))
- **device-viewer**: gap under the Zones section header ([`3e21a93`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3e21a93cf454b6525c24ef4d8b32fee67bb2140a))
- **device-viewer**: drag-move regions with multi-select on ([`538c750`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/538c750598340e220660f34b3745e346c43edcec))
- **device-viewer**: regions table shows the zone's current name ([`0a2934c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/0a2934cac5cf8e3320722981920d04cc40f00067))
- **device-viewer**: report trimmed zone regions on load ([`ab52f01`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ab52f01948ecfbde913741e01d9c0cc133b68be6))
- **examples**: demo cancels zones only when leaving the tools ([`d4f4921`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d4f4921514ca894abdf66d6b2edf3e02229ffd99))
- **device-viewer**: guard zone overlay teardown ([`f9e872e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f9e872ec14f4f6cad39872ef52c5b2decbb8db74))
- **device-viewer**: uncap zone undo history ([`efd8877`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/efd88773b5427895d8eb57dec2e2fcb99b945d64))
- **device-viewer**: keep zone channels in step with edits ([`53bee9e`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/53bee9e7bc4d71abdb66ea634d3d084e74a16b4d))
- **device-viewer**: drop zone gestures on mode change ([`a46eaf6`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a46eaf6e9607d64d0e27b14e7a97d98e25c88a75))
- **device-viewer**: Off restores the pre-zone-tool mode ([`59c3c53`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/59c3c53552d70e8a711bf3bd8ab5f3de3570d7cb))
- **device-viewer**: seed zone types with advancing colors ([`b012dd5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b012dd572829f6a812ebe309ef01496d2335a482))
- **device-viewer**: no undo snapshot for unknown zone type ([`db064ac`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/db064ac75a1a85b5164d65d814331e107d937058))

### Refactor

- **device-viewer**: canvas strips reuse button labels ([`2cc9fd8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2cc9fd8bb7d0e34eef851d3a05a826a64e3820b6))
- **device-viewer**: zone name column at content width ([`fcf96ea`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/fcf96eaf934bc73f32033764423fe6717667427b))
- **device-viewer**: zones sidebar on TraitsUI editors ([`09bf2d0`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/09bf2d0007653f11232cc261688e0becdf2afe2d))
- **device-viewer**: zones section below Paths ([`eb4c1cf`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eb4c1cf605a9bcea746283658171d41605a6ca5c))
- **device-viewer**: zone tools as one row like Paths ([`a3fe2e8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a3fe2e8976d2bcb3edeb4d72d36d655453063578))
- **device-viewer**: glyph labels for zone buttons ([`4682045`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/46820457f17c050bb4fc13e493009e08e412bf42))
- **device-viewer**: zones section sits above Paths ([`3e29808`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3e29808af22e40c74cf9bd434ae6310f18e6140c))
- **device-viewer**: zone canvas actions hygiene ([`ea8d653`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/ea8d653dcf880c19ebbe6f749a281244b62392a3))
- **examples**: demo uses the shipped overlay strip ([`362303a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/362303ac710fc0f78fbc996512bf2a70f7658a42))
- **device-viewer**: zone canvas actions helper ([`d540963`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/d540963a1fee19db3eaffe45a90f5ad53c39d88d))
- **device-viewer**: zone model polish and tests ([`3afada4`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3afada4205583bcaa3acfa64ad476d1e68fd4763))
- **examples**: zones demo reuses the shipped model ([`c9cc32c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/c9cc32cee232d7f267b551cf3c12e7355757c8d9))
- **device-viewer**: use mode constants in zones view ([`79cc425`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/79cc4255a709a2be6a0974ab73136055680074cd))

### Docs

- zones spec reflects the shipped wiring ([`bf74b21`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/bf74b213d3e11a9bcb97fe615e105176780e6185))
- **device-viewer**: explain the zone reposition guard ([`972c5b2`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/972c5b23c09c1d88d7724ae4a29304567824255e))
- **device-viewer**: tidy zone pointers and teardown docs ([`5838b83`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5838b83573b592923fdc9f5abcda41d40ab366d8))
- point at the electrode zones implementation ([`2497d1a`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/2497d1ae173e6adaa8da106f4607386bc3b6bf3b))
- spec for electrode zones ([`59d574c`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/59d574cd1b67668f375650342c9940ff367aa829))

## [v1.18.0](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v1.18.0) (2026-09-03)

### Feat

- **device-viewer**: add opt-in gamepad preference ([`b9f9f66`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b9f9f662ca4a7cfab6686539a7d6f52860de508e))

### Fix

- **device-viewer**: hide the joystick icon while gamepad support is off ([`85cac63`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/85cac63d3d825d7b03d21efe6093f1a3e32bd572))
- **device-viewer**: rename alignment helper to Align Camera ([`5583ee8`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5583ee88535f2813ea0fbe3ec18a33d3fedd2236))
- **device-viewer**: align endpoint buttons with camera rows ([`a673b55`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/a673b5591c430a03d592ed98d6450cb776a9ae3f))

### Refactor

- **device-viewer**: split gamepad and stepping services ([`3eaa97f`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/3eaa97f06ea0500ac726d4479321382704bfa94e))

### Docs

- **changelog**: regenerate with commit links ([`b9e3b13`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/b9e3b13bfeacaa0edbaf6613dc394fe3a76b09d0))
- **readme**: sync launcher downloads and add the portable device ([`eb1e3a5`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/eb1e3a582efed9ecc4e7a7fa74545c615ab63c0e))

### CI

- **release**: keep bump commits out of the changelog ([`8b4b5b9`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/8b4b5b98b6d202ae7a67025ce4cc04fc4c9c1bac))
- **release**: link changelog entries to commits ([`776f2f1`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/776f2f10f8897fc68975f23a1d7cf452cdcae024))
- **release**: describe the app-token setup in the workflow notes ([`f68a539`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/f68a5397def03da7cecba60c530ff569b1e2c42f))
- **release**: open the release PR with the org release app ([`cc9a528`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/cc9a528edb89b9c98ddce7c8f610335219d6bf60))

### Chore

- **device-viewer**: ruff-clean preferences.py ([`60efcdc`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/60efcdcc9df2f6b4d0ad137631c76f0d682a7c1b))
- **device-viewer**: bring the device view dock pane ruff-clean ([`5a9ee9b`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/commit/5a9ee9b23d61c4c1aed88dc8b193d96f23c6c0cd))

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
