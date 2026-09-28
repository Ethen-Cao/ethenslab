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
| Bluetooth HFP Client | `android/android/packages/modules/Bluetooth/android/app/src/com/android/bluetooth/hfpclient/HeadsetClientService.java`; `HeadsetClientStateMachine.java` in the same directory | `HeadsetClientService extends ProfileService`; dial/accept/reject/terminate APIs. State machine calls AudioManager `setHfpEnabled`, `setHfpSamplingRate`, `setHfpVolume`. Placed in Framework / System Services; its HAL edge collapses intervening framework calls. |
| HAL and PAL | `android/android/vendor/qcom/opensource/audio-hal-ar/primary-hal/hal-pal/AudioDevice.cpp`; `audio_extn/AudioExtn.cpp` | Stream/parameter APIs, HFP parameters, PAL calls and output-stream mute callback. |
| AudioControl AIDL | `android/android/vendor/voyah/hardware/common/audiocontrol/aidl/default/AudioControl.cpp`; `aidl/client/AudioControlClient.cpp` | `onDevicesToMuteChange` invokes `onAudioMuteChanged`; `AudioExtn::onAudioMuteChangedInfo` calls `SetOutputMute`. |
| PAL → AGM | `android/android/vendor/qcom/opensource/pal/session/src/SessionAgm.cpp`; `pal/Android.mk` | AGM session metadata/open/config/read-write callback APIs; client library dependency. |
| AGM → GSL | `android/android/vendor/qcom/opensource/agm/service/src/graph.c` | `gsl_open`, `gsl_ioctl`, graph read/write. Guest MMHAB transport is supported by the design and QNX peer implementation; guest library internals are not fully audited. |

## Explicit limits

- `avas_service` has design evidence, but its project implementation and deployment were not found. The block and edge are brown dashed references.
- Radio → Android is documented as USB audio. Paired `RADIO` ports express this reference path without implying the missing project HAL implementation was verified.
- The audited AudioControl duck callback logs requests; it must not be presented as an implemented attenuation path. Mute has an actual callback to the HAL.
- The document describes media volume at the external amplifier. The full vehicle-property/CAN/MCU mapping was not established, so no speculative MCU or bus chain is drawn.
- ECNS bypass in the document and `capi_ecns.so` in the image are different kinds of evidence. Neither proves current runtime activation. DSP internals are therefore shown as audio graphs, not an asserted active ECNS chain.
- `A2B` and `MIC` matched ports connect each software driver to its hardware device for I2C/GPIO control and fault state. Orange lines carry audio/stream APIs; blue lines carry control; purple is HAB; brown dashed paths are document-only references.
- Hardware sample arrows describe the intended audio direction: playback toward the amplifier, capture toward the DSP, Bluetooth call audio in both directions. Bidirectional software stream edges summarize playback and capture rather than claiming every stream or bus is full duplex.
