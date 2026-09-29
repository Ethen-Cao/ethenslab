# Audio architecture evidence

The Audio child view maps **Audio design document v1.5 (2025-02-19)** to the available HBEZ source tree. Repository paths below are relative to `/home/ethen/workspace/HBEZ`. It describes source/configuration evidence, not a runtime trace of a flashed vehicle.

## Design reference

Source: `/home/ethen/Documents/TechnologyDocuments/voyah/岚图8295 Audio 设计文档.pdf`.

- Page 4: QNX / Android / ADSP overview, CSD2, Audio Framework, PAL/AGM/MMHAB, external A2B, microphone ADC, Bluetooth and USB radio paths.
- Pages 6–10: playback/capture, audio bus routing, volume and mute interfaces.
- Page 11: Bluetooth call loopback in ADSP; the document describes ECNS as bypass at that revision.
- Page 12: Chime and AVAS APIs. The diagram maps chime to the actual project `audiomgr` implementation rather than inventing a separate `chime_play` deployment.
- Pages 13–20: A2B discovery, slot configuration, diagnostics and power lifecycle.
- Pages 21–23: PCM6xx0 microphone ADC configuration, diagnostics and suspend/resume.
- Pages 24 onward: radio integration. Its complete project-specific HAL/USB path was not established in this audit.

## Source and image evidence

| Diagram component / edge | Evidence | Scope |
|---|---|---|
| `libaudiomgr_if` ↔ `audiomgr` | `cluster_source_code/platforms/audiomgr/src/audiomgr_api.c`; `src/audiomgr_local.c`; `src/inner_priorityQue.c` | Project IPC, notifications, queue handling. |
| `audiomgr` → CSD2 client | `cluster_source_code/platforms/audiomgr/cmake/audiomgr_qnx.cmake`; `src/audiomgr_player.c`; `src/csd2pcm_player.c` | Default `CSD_TYPE=csd2`; links `csd2IpcClient`; open/ioctl/buffer operations. Build variants can select another backend. |
| Project `audiomgr` deployment | `cluster/prebuilts/HBEZ/usr/etc/slm/audiomgr.xml` | SLM starts `/mnt/usr/bin/audiomgr`. |
| `audio_service` and CSD2 IPC | `bsp/apps/qnx_ap/AMSS/multimedia/audio/audio_ar/audio_service/src/coreinit.c`; `audio_driver/csd2_ipc/csd2IpcServer/csd2_proxy_msgParser.c` | Runtime initializes CSD2 and GSL backend; resource-manager requests and callbacks. |
| QNX audio executable | `bsp/apps/qnx_ap/target/hypervisor/host/out_8540/ifs_audio.build` | Despite the output directory name, this manifest maps `audio_service` to `audio_service-s8295-ar-qvmhost`. This is packaging evidence, not a live-process observation. |
| GSL HAB backend | `bsp/apps/qnx_ap/AMSS/multimedia/audio/audio_ar/audio_driver/gsl_be/src/gsl_be.c`; `gsl_vm_be.c` | HAB request/reply sockets, event path, out-of-band shared-memory import/export. Backend is initialized within the audio runtime; graph blocks are not separate process claims. |
| DSP transport | `bsp/apps/qnx_ap/AMSS/multimedia/audio/audio_ar/audio_driver/csd2/modules/utils/common/inc/csd2_gpr_common.h` and associated implementation | GPR/SPF command/response wrapper. Kept separate from host/guest HAB. |
| Codec service | `bsp/vendor/voyah_base/audio/audio_codec/codec_service/src/main.c` | Board configuration, driver client/plugin processing, process monitoring and low-power registration. |
| Codec deployment | `bsp/vendor/voyah_base/common/voyah.system.build` | `codec_service`, `liba2b_amp`, `liba2b_common`, `libpcm6xx0`, ACDB and `capi_ecns.so` are packaged. Packaging an algorithm does not establish it is enabled. |
| A2B driver | `bsp/vendor/voyah_base/audio/audio_codec/codec_driver/a2b_amp/src/a2bapp_main.c`; `a2b_common/src/a2bapp.c`; `a2b_common/src/a2bapp_diag.c` | Discovery, register configuration, link faults and `/dev/a2b`. |
| Microphone ADC driver | `bsp/vendor/voyah_base/audio/audio_codec/codec_driver/pcm6xx0/src/pcm6xx0.c` | I2C register operations, low-power checks, capture-device configuration. Device family used because document names vary. |
| Audio configuration | `bsp/vendor/voyah_base/audio/config/audio_oem_cfg/audio_oem.cfg`; `config/acdb_oem_datafiles/` | Startup devices, channel/format and calibration data. No hard-coded cross-platform slot count. |
| Car audio policy | `android/android/packages/services/Car/service/src/com/android/car/audio/CarAudioService.java`; `CarVolumeGroupMuting.java`; `CarDucking.java` | Zones/groups/focus and AudioControl mute/duck interfaces. |
| Android native framework | `android/android/frameworks/av/services/audioflinger/`; `services/audiopolicy/` | Native playback/record threads and policy service. The diagram abstracts wrapper calls rather than identifying every Binder hop. |
| Bluetooth HFP Client | `android/android/packages/modules/Bluetooth/android/app/src/com/android/bluetooth/hfpclient/HeadsetClientService.java`; `HeadsetClientStateMachine.java` in the same directory | `HeadsetClientService extends ProfileService`; dial/accept/reject/terminate APIs. State machine calls AudioManager `setHfpEnabled`, `setHfpSamplingRate`, `setHfpVolume`. Placed in Framework / System Services; separate edges expose the native Bluetooth protocol path and AudioManager parameter path. |
| HFP JNI / profile interface | `android/android/packages/modules/Bluetooth/android/app/jni/com_android_bluetooth_hfpclient.cpp`; `android/android/packages/modules/Bluetooth/system/include/hardware/bt_hf_client.h` | `get_profile_interface(BT_PROFILE_HANDSFREE_CLIENT_ID)` supplies `bthf_client_interface_t`; JNI forwards commands and callbacks. This is not a standalone vendor HFP HAL service. |
| Native Bluetooth HFP stack | `android/android/packages/modules/Bluetooth/system/btif/src/btif_hf_client.cc`; `android/android/packages/modules/Bluetooth/system/bta/hf_client/bta_hf_client_sco.cc` | `connect_audio` / `disconnect_audio` call `BTA_HfClientAudioOpen/Close`; protocol and SCO/eSCO management belong to the native stack. |
| Bluetooth HCI HAL boundary | `android/android/packages/modules/Bluetooth/system/gd/hal/hci_hal_android_hidl.cc` | `IBluetoothHci`, sendHciCommand and callback handling establish the controller boundary. The diagram leaves the deployed HAL version and board UART/USB transport binding unspecified. It does not draw HCI HAL calling Audio HAL. |
| AudioManager and native AudioSystem | `android/android/frameworks/base/media/java/android/media/AudioManager.java`; `android/android/frameworks/av/media/libaudioclient/AudioSystem.cpp` | HFP enable/rate/volume APIs call AudioSystem.setParameters; native AudioSystem calls AudioFlinger setParameters through Binder. AudioManager is in Framework, AudioSystem in Native Services & Libraries. |
| AudioFlinger parameter forwarding | `android/android/frameworks/av/services/audioflinger/AudioFlinger.cpp` | Global setParameters iterates hardware devices and calls DeviceHalInterface::setParameters. Parameter control has a separate edge from playback/record stream I/O. |
| Audio HAL HFP extension | `android/android/vendor/qcom/opensource/audio-hal-ar/primary-hal/hal-pal/audio_extn/AudioExtn.cpp`; `audio_extn/Hfp.cpp`; `audio_extn/Android.mk` in the same HAL directory | AudioDevice::SetParameters calls AudioExtn; it loads libhfp_pal.so and dispatches hfp_set_parameters. Hfp.cpp builds PAL_STREAM_LOOPBACK_HFP_RX/TX. AudioDevice and HFP Extension are enclosed by Audio HAL Implementation, not depicted as independent HAL services. |
| HAL and PAL | `android/android/vendor/qcom/opensource/audio-hal-ar/primary-hal/hal-pal/AudioDevice.cpp`; `audio_extn/AudioExtn.cpp` | Stream/parameter APIs, HFP parameters, PAL calls and output-stream mute callback. |
| AudioControl AIDL | `android/android/vendor/voyah/hardware/common/audiocontrol/aidl/default/AudioControl.cpp`; `aidl/client/AudioControlClient.cpp` | `onDevicesToMuteChange` invokes `onAudioMuteChanged`; `AudioExtn::onAudioMuteChangedInfo` calls `SetOutputMute`. |
| PAL → AGM | `android/android/vendor/qcom/opensource/pal/session/src/Session.cpp`; `SessionAlsaPcm.cpp`; `SessionAlsaUtils.cpp`; AGM tinyalsa plugin | PLAYBACK_BUS uses SessionAlsaPcm and AGM plugin metadata/FE-BE connection APIs. SessionAgm is used for NON_TUNNEL. |
| AGM → GSL | `android/android/vendor/qcom/opensource/agm/service/src/graph.c` | `gsl_open`, `gsl_ioctl`, graph read/write. Guest MMHAB transport is supported by the design and QNX peer implementation; guest library internals are not fully audited. |

## Explicit limits

- `avas_service` has design evidence, but its project implementation and deployment were not found. The block and edge are brown dashed references.
- Radio → Android is documented as USB audio. Paired `RADIO` ports express this reference path without implying the missing project HAL implementation was verified.
- The audited AudioControl duck callback logs requests; it must not be presented as an implemented attenuation path. Mute has an actual callback to the HAL.
- The document describes media volume at the external amplifier. The full vehicle-property/CAN/MCU mapping was not established, so no speculative MCU or bus chain is drawn.
- ECNS bypass in the document and `capi_ecns.so` in the image are different kinds of evidence. Neither proves current runtime activation. DSP internals are therefore shown as audio graphs, not an asserted active ECNS chain.
- `A2B` and `MIC` matched ports connect each software driver to its hardware device for I2C/GPIO control and fault state. Orange lines carry audio/stream APIs; blue lines carry control; purple is HAB; brown dashed paths are document-only references.
- Hardware sample arrows describe the intended audio direction: playback toward the amplifier, capture toward the DSP, Bluetooth call audio in both directions. Bidirectional software stream edges summarize playback and capture rather than claiming every stream or bus is full duplex.

## Diagram dependency checks

The HFP Client has two outgoing dependency branches: JNI/Profile → native Bluetooth Stack → HCI HAL → Bluetooth Controller, and AudioManager → native AudioSystem → AudioFlinger → AudioDevice → HFP Extension → PAL. HCI command/event traffic and I2S speech samples use different controller ports. Both Bluetooth control and I2S speech are included in the Bluetooth Call filter. The existing Audio System parent entry keeps its own identifier, separate from the newly added native AudioSystem module.

## Bus / BE / TDM audit (2026-09-29)

The Audio page now separates **Component interactions** from **Bus / BE / TDM routing**. The routing panel is a source/configuration audit, not a route dump from a running target. Its frozen input is `audio-routing-data.json`; each source has its repository-relative path and SHA-256. The generated HTML embeds the snapshot and needs no network request.

### Bus identity, backend identity, and graph identity

- `configs/nurburgring/nurburgring.mk:59` selects the HBEZ `car_audio_configuration.xml` when `VEHICLE_MODEL=HBEZ`. The selected Car configuration defines contexts/zones; `configs/nurburgring/audio_policy_configuration.xml:263` declares 13 output bus devicePorts and two input bus devicePorts.
- `hal-pal/AudioStream.cpp:3807` passes the address when initially resolving output devices. `AudioDevice.cpp:2337` maps the ordinary output buses to `PAL_DEVICE_OUT_SPEAKER`, front passenger to `PAL_DEVICE_OUT_A2B_SPKR`, and rear seat to `PAL_DEVICE_OUT_A2B2_SPKR`. Other routing overrides, including AG SCO and external-device changes, can alter the runtime route; the register describes the default bus opening path.
- `auto-casa-xml/usecaseKvManager.xml:307` maps the bus to STREAMRX (`0xA1000000`); the device table maps PAL devices to DEVICERX (`0xA2000000`). The speaker devicepp table at line 535 supplies bus-specific DEVICEPP_RX (`0xAC000000`). Notification and navigation intentionally have the same processing value in the actual XML (`0xAC000007`) while retaining different STREAMRX values. Comments with mismatched bus names are not used as values.
- The audited `resourcemanager_gvmauto8295_adp_star.xml` maps `PAL_DEVICE_OUT_SPEAKER` to `TDM-LPAIF_RXTX-RX-PRIMARY`, 48 kHz, 32-bit, 16 channels. **The file does not define the two A2B output device profiles.** Their BE names and formats remain unknown. ResourceManager's default LUT entries for those devices are empty. This is a configuration gap in this candidate profile, not proof that all deployed variants have broken routing.
- BUS2001_VENDOR_CALL_RING is declared in policy/KV but not assigned in the selected HBEZ Car configuration, where `call_ring` belongs to BUS03_PHONE. These are kept distinct from the older document's simplified bus labels.
- Input bus default resolution uses `PAL_DEVICE_IN_HANDSET_MIC` (`AudioDevice.cpp:2291`); the audited profile assigns `TDM-LPAIF_AUD-TX-PRIMARY`. ECHO_REFERENCE maps to `PAL_DEVICE_IN_ASR_MIC` and shares that BE name but has a different device graph key. Application capture extraction/ordering is not derived from the profile's 16-channel transport format.

### Corrected session and ADSP route model

The earlier PAL evidence row generalized `SessionAgm` too broadly. `Session::makeSession` (`pal/session/src/Session.cpp:109`) selects `SessionAlsaPcm` for ordinary PLAYBACK_BUS and loopback types; `SessionAgm` is selected for NON_TUNNEL. `SessionAlsaPcm::open` gets backend names from ResourceManager. `SessionAlsaUtils.cpp:359–513` constructs stream/device metadata and selects the BE with FE Connect; `agm/plugins/tinyalsa/src/agm_mixer_plugin.c:967–1167` forwards metadata and connection operations into AGM. These are library/plugin calls, not proof of a physical Linux ALSA audio device in the guest.

`agm/service/src/session_obj.c:701` merges session, session-AIF and device metadata before opening the graph; `graph.c:652` calls `gsl_open` with graph and calibration vectors. GSL/HAB reaches the QNX backend and DSP. The document's mixing/demux and reference paths are architectural intent; exact ACDB graph topology, coefficients, active algorithms and per-bus output slot matrix have not been decoded in this audit.

`VendorAudioExtn.cpp` adds runtime routing parameters: `CustomVersion` enables the ALS branch only for V3. `AlsSyncSpeakerMode` applies speaker-mode tags to navigation/assistant/phone paths and media parameters such as EQ/fader/balance to media. `send_kv_payload` sends TKV via `PAL_PARAM_ID_UIEFFECT`. `SyncMicMode` sends CHANNELS with DEVICE_MUX_DEMUX when micMode is nonzero; that value is not treated as a physical slot bitmask. `SyncRefMode` has a voice-recognition path; its HFP reference branch is commented out. The existence of these calls does not confirm the target's active feature flags or algorithm state.

`Hfp.cpp:295–379` pairs HFP downlink input with speaker output and handset MIC input with HFP uplink output. BUS99_HFP_DOWNLINK/BUS98_HFP_UPLINK are internal labels for parameter synchronization here, not additional Car policy devicePorts. PayloadBuilder skips bus-address selection for loopback streams. Therefore the HFP speech loopback is not modeled as application PCM on BUS03_PHONE.

### Verified peripheral slot configuration

- Board file `boards/core/dalconfig/sa8295P_qam_pats_v1.0.3/local_config/devcfg_audio.xml:85–113`: ASI format 0 (TDM), slot width 3 (32-bit), channel switch `0x3F`, slot mapping `0x542310`.
- `pcm6xx0.c:714–730` extracts one nibble per hardware MIC channel. MIC1–6 map to slots **0, 1, 3, 2, 4, 5**. Slot order is MIC1, MIC2, MIC4, MIC3, MIC5, MIC6. The source document page 6 likewise swaps the two second-row hardware MIC labels. Neither establishes the final application-visible channel layout without DSP graph evidence.
- `a2bapp_callback.c:9–37` currently returns `0x3`; the ECU-selection code is inside `#if 0`. The default branch at line 79 selects the TDM16 configuration audited in the snapshot. The alternate branch is not claimed active.
- Its BCF sets the master and slave to TDM16/32-bit. Stream declarations at lines 1289–1465 define 16 downstream slots and four upstream slots, 48 kHz, start index 0, 32-bit data. Source/sink stream declarations agree. **No business or physical loudspeaker meaning is assigned to those slot numbers without the ChannelMap.** The alternate configuration filename containing “tdm8” is not used to overwrite the selected master's mode.
- `audio_oem.cfg` contains startup clk_id 4/7/17, each 48 kHz / 32-bit / 16 channels. These IDs are not TDM slot indices.
- SPF's `pcm_tdm_api.h:368–470` defines `PARAM_ID_TDM_INTF_CFG`, active slot mask, slots per frame, width and lane configuration. API defaults are not project settings. ACDB/delta/workspace files are binary; their actual endpoint parameters and mixer matrices were not decoded. A 24.576 MHz BCLK is shown only as the conditional calculation 48 kHz × 16 × 32 for a full single-lane frame, not a measurement.

### Still required for a complete business-to-speaker mapping

1. The A2B input/output ChannelMap referenced by the design document, section 2.2.
2. Export of the matching ACDB graph/channel matrices and effective TDM endpoint/lane parameters.
3. Runtime-selected resource profile and AIF/graph-key/tag information, plus firmware/ACDB versions and peripheral register readback.

Until those are available, the page deliberately shows `unknown` for bus-to-slot/speaker allocation, BT slot numbers, A2B upstream signal purpose and the missing zonal backend bindings.
