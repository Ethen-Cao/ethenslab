---
title: "ActivityManager 深度解析"
date: 2024-07-29T10:00:00+08:00 
draft: true
---

ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  * Task{21a4759 #1 type=home U=0 visible=true visibleRequested=true mode=fullscreen translucent=false sz=1}
    * Task{836b5dc #211 type=home I=com.android.launcher3/.uioverrides.QuickstepLauncher U=0 rootTaskId=1 visible=true visibleRequested=true mode=fullscreen translucent=false sz=1}
      mLastPausedActivity: ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}
      mLastNonFullscreenBounds=Rect(260, 635 - 821, 1715)
      isSleeping=false
      topResumedActivity=ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}
      * Hist  #0: ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}
        packageName=com.android.launcher3 processName=com.android.launcher3
        launchedFromUid=0 launchedFromPackage=null launchedFromFeature=null userId=0
        app=ProcessRecord{7863d74 2961:com.android.launcher3/u0a134}
        Intent { act=android.intent.action.MAIN cat=[android.intent.category.HOME] flg=0x10000100 cmp=com.android.launcher3/.uioverrides.QuickstepLauncher (has extras) }
        rootOfTask=true task=Task{836b5dc #211 type=home I=com.android.launcher3/.uioverrides.QuickstepLauncher}
        taskAffinity=null
        mActivityComponent=com.android.launcher3/.uioverrides.QuickstepLauncher
        baseDir=/system_ext/priv-app/Launcher3QuickStep/Launcher3QuickStep.apk
        dataDir=/data/user/0/com.android.launcher3
        stateNotNeeded=true componentSpecified=false mActivityType=home
        compat={420dpi} labelRes=0x7f11008e icon=0x7f080270 theme=0x7f12000c
        mLastReportedConfigurations:
          mGlobalConfig={1.0 ?mcc0mnc [en_US] ldltr sw411dp w411dp h792dp 420dpi nrml long hdr widecg port finger -keyb/v/h -nav/h winConfig={ mBounds=Rect(0, 0 - 1080, 2340) mAppBounds=Rect(0, 136 - 1080, 2214) mMaxBounds=Rect(0, 0 - 1080, 2340) mDisplayRotation=ROTATION_0 mWindowingMode=fullscreen mDisplayWindowingMode=fullscreen mActivityType=undefined mAlwaysOnTop=undefined mRotation=ROTATION_0} s.15 fontWeightAdjustment=0}
          mOverrideConfig={1.0 ?mcc0mnc [en_US] ldltr sw411dp w411dp h792dp 420dpi nrml long hdr widecg port finger -keyb/v/h -nav/h winConfig={ mBounds=Rect(0, 0 - 1080, 2340) mAppBounds=Rect(0, 136 - 1080, 2214) mMaxBounds=Rect(0, 0 - 1080, 2340) mDisplayRotation=ROTATION_0 mWindowingMode=fullscreen mDisplayWindowingMode=fullscreen mActivityType=home mAlwaysOnTop=undefined mRotation=ROTATION_0} s.2 fontWeightAdjustment=0}
        CurrentConfiguration={1.0 ?mcc0mnc [en_US] ldltr sw411dp w411dp h792dp 420dpi nrml long hdr widecg port finger -keyb/v/h -nav/h winConfig={ mBounds=Rect(0, 0 - 1080, 2340) mAppBounds=Rect(0, 136 - 1080, 2214) mMaxBounds=Rect(0, 0 - 1080, 2340) mDisplayRotation=ROTATION_0 mWindowingMode=fullscreen mDisplayWindowingMode=fullscreen mActivityType=home mAlwaysOnTop=undefined mRotation=ROTATION_0} s.2 fontWeightAdjustment=0}
        RequestedOverrideConfiguration={0.0 ?mcc0mnc ?localeList ?layoutDir ?swdp ?wdp ?hdp ?density ?lsize ?long ?ldr ?wideColorGamut ?orien ?uimode ?night ?touch ?keyb/?/? ?nav/? winConfig={ mBounds=Rect(0, 0 - 0, 0) mAppBounds=null mMaxBounds=Rect(0, 0 - 0, 0) mDisplayRotation=undefined mWindowingMode=undefined mDisplayWindowingMode=undefined mActivityType=home mAlwaysOnTop=undefined mRotation=undefined} ?fontWeightAdjustment}
        taskDescription: label="null" icon=null iconResource=/0 iconFilename=null primaryColor=fff2f1e5
          backgroundColor=fff2f1e5 statusBarColor=0 navigationBarColor=0
         backgroundColorFloating=fff2f1e5
        launchFailed=false launchCount=0 lastLaunchTime=-9m20s147ms
        mHaveState=false mIcicle=null
        state=RESUMED delayedResume=false finishing=false
        keysPaused=false inHistory=true idle=true
        occludesParent=true noDisplay=false immersive=false launchMode=2
        frozenBeforeDestroy=false forceNewConfig=false
        mActivityType=home
        mImeInsetsFrozenUntilStartInput=false
        windows=[Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}]
        windowType=2 waitingToShow=true
        mOccludesParent=true
        overrideOrientation=SCREEN_ORIENTATION_NOSENSOR
        requestedOrientation=SCREEN_ORIENTATION_NOSENSOR
        mVisibleRequested=true mVisible=true mClientVisible=true reportedDrawn=true reportedVisible=true
        mNumInterestingWindows=1 mNumDrawnWindows=1 allDrawn=true lastAllDrawn=true)
        startingData=null firstWindowDrawn=true mIsExiting=false
        nowVisible=true lastVisibleTime=-1m3s817ms
        connections={ConnectionRecord{bc23dfe u0 com.android.launcher3/com.android.quickstep.TouchInteractionService:@f9045b9 flags=0x0}}
        resizeMode=RESIZE_MODE_RESIZEABLE
        mLastReportedMultiWindowMode=false mLastReportedPictureInPictureMode=false
        supportsSizeChanges=SIZE_CHANGES_UNSUPPORTED_METADATA
        configChanges=0xdf3
        neverSandboxDisplayApis=false
        alwaysSandboxDisplayApis=false
        areBoundsLetterboxed=false
        mCameraCompatControlState=hidden
        mCameraCompatControlEnabled=false

  * Task{46e36e5 #2 type=undefined U=0 visible=false visibleRequested=false mode=fullscreen translucent=true sz=2}
    mCreatedByOrganizer=true
    * Task{bfea16a #4 type=undefined U=0 rootTaskId=2 visible=false visibleRequested=false mode=multi-window translucent=true sz=0}
      mBounds=Rect(0, 2340 - 1080, 3510)
      mCreatedByOrganizer=true
      isSleeping=false
    * Task{f47a3e0 #3 type=undefined U=0 rootTaskId=2 visible=false visibleRequested=false mode=multi-window translucent=true sz=0}
      mCreatedByOrganizer=true
      isSleeping=false

  Resumed activities in task display areas (from top to bottom):
    Resumed: ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}

  ResumedActivity: ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}

ActivityTaskSupervisor state:
  topDisplayFocusedRootTask=Task{21a4759 #1 type=home}
  Display: mDisplayId=0 (organized)
    init=1080x2340 420dpi mMinSizeOfResizeableTaskDp=220 cur=1080x2340 app=1080x2078 rng=1080x1006-2078x2078
    deferred=false mLayoutNeeded=false mTouchExcludeRegion=SkRegion((0,0,1080,2340))

  mLastOrientationSource=WindowedMagnification:0:31@208462429
  deepestLastOrientationSource=ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}
  overrideConfig={1.0 ?mcc0mnc [en_US] ldltr sw411dp w411dp h792dp 420dpi nrml long hdr widecg port finger -keyb/v/h -nav/h winConfig={ mBounds=Rect(0, 0 - 1080, 2340) mAppBounds=Rect(0, 136 - 1080, 2214) mMaxBounds=Rect(0, 0 - 1080, 2340) mDisplayRotation=ROTATION_0 mWindowingMode=fullscreen mDisplayWindowingMode=fullscreen mActivityType=undefined mAlwaysOnTop=undefined mRotation=ROTATION_0} s.13 fontWeightAdjustment=0}
  mLayoutSeq=108
  mCurrentFocus=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
  mFocusedApp=ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}

  mHoldScreenWindow=null
  mObscuringWindow=Window{4c7d178 u0 com.android.systemui.wallpapers.ImageWallpaper}
  mLastWakeLockHoldingWindow=null
  mLastWakeLockObscuringWindow=null

  displayId=0
  mWallpaperTarget=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
  mLastWallpaperX=0.0 mLastWallpaperY=0.5

  Display areas in top down Z order:
    * Leaf:36:36
    * HideDisplayCutout:32:35
      * OneHanded:34:35
        * FullscreenMagnification:34:35
          * Leaf:34:35
      * FullscreenMagnification:33:33
        * Leaf:33:33
      * OneHanded:32:32
        * Leaf:32:32
    * WindowedMagnification:0:31
      * HideDisplayCutout:26:31
        * OneHanded:26:31
          * FullscreenMagnification:29:31
            * Leaf:29:31
          * Leaf:28:28
          * FullscreenMagnification:26:27
            * Leaf:26:27
      * Leaf:24:25
      * HideDisplayCutout:18:23
        * OneHanded:18:23
          * FullscreenMagnification:18:23
            * Leaf:18:23
      * OneHanded:17:17
        * FullscreenMagnification:17:17
          * Leaf:17:17
      * HideDisplayCutout:16:16
        * OneHanded:16:16
          * FullscreenMagnification:16:16
            * Leaf:16:16
      * OneHanded:15:15
        * FullscreenMagnification:15:15
          * Leaf:15:15
      * HideDisplayCutout:0:14
        * OneHanded:0:14
          * ImePlaceholder:13:14
            * ImeContainer
          * FullscreenMagnification:0:12
            * Leaf:3:12
            * DefaultTaskDisplayArea (organized)
            * Leaf:0:1

  Task display areas in top down Z order:
    TaskDisplayArea DefaultTaskDisplayArea
      overrideConfig={0.0 ?mcc0mnc ?localeList ?layoutDir ?swdp ?wdp ?hdp ?density ?lsize ?long ?ldr ?wideColorGamut ?orien ?uimode ?night ?touch ?keyb/?/? ?nav/? winConfig={ mBounds=Rect(0, 0 - 0, 0) mAppBounds=null mMaxBounds=Rect(0, 0 - 0, 0) mDisplayRotation=undefined mWindowingMode=fullscreen mDisplayWindowingMode=fullscreen mActivityType=undefined mAlwaysOnTop=undefined mRotation=undefined} ?fontWeightAdjustment}
      mPreferredTopFocusableRootTask=Task{21a4759 #1 type=home}
      mLastFocusedRootTask=Task{21a4759 #1 type=home}
      Application tokens in top down Z order:
      * Task{21a4759 #1 type=home U=0 visible=true visibleRequested=true mode=fullscreen translucent=false sz=1}
        bounds=[0,0][1080,2340]
        * Task{836b5dc #211 type=home I=com.android.launcher3/.uioverrides.QuickstepLauncher U=0 rootTaskId=1 visible=true visibleRequested=true mode=fullscreen translucent=false sz=1}
          bounds=[0,0][1080,2340]
          * ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}
      * Task{46e36e5 #2 type=undefined U=0 visible=false visibleRequested=false mode=fullscreen translucent=true sz=2}
        bounds=[0,0][1080,2340]
        * Task{bfea16a #4 type=undefined U=0 rootTaskId=2 visible=false visibleRequested=false mode=multi-window translucent=true sz=0}
          bounds=[0,2340][1080,3510]
        * Task{f47a3e0 #3 type=undefined U=0 rootTaskId=2 visible=false visibleRequested=false mode=multi-window translucent=true sz=0}
          bounds=[0,0][1080,2340]

  no ScreenRotationAnimation 

  rootHomeTask=Task=1

  PinnedTaskController
    mIsImeShowing=false
    mImeHeight=0
    mMinAspectRatio=0.41841003
    mMaxAspectRatio=2.39

  DisplayFrames w=1080 h=2340 r=0

  DisplayPolicy
    mCarDockEnablesAccelerometer=true mDeskDockEnablesAccelerometer=true
    mDockMode=EXTRA_DOCK_STATE_UNDOCKED mLidState=LID_ABSENT
    mAwake=true mScreenOnEarly=true mScreenOnFully=true
    mKeyguardDrawComplete=true mWindowManagerDrawComplete=true
    mHdmiPlugged=false
    mLastBehavior=DEFAULT
    mShowingDream=false mDreamingLockscreen=false
    mStatusBar=Window{32f3e94 u0 StatusBar}
    mExpandedPanel=Window{91c910b u0 NotificationShade}
    isKeyguardShowing=false
    mNavigationBar=Window{6dc8727 u0 NavigationBar0}
    mNavBarOpacityMode=0
    mNavigationBarCanMove=true
    mNavigationBarPosition=4
    mTopGestureHost=Window{32f3e94 u0 StatusBar}
    mBottomGestureHost=Window{6dc8727 u0 NavigationBar0}
    mFocusedWindow=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
    mTopFullscreenOpaqueWindowState=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
    mSystemBarColorApps={ActivityRecord{6fa5a4f u0 com.android.launcher3/.uioverrides.QuickstepLauncher t211}}
    mNavBarColorWindowCandidate=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
    mNavBarBackgroundWindow=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
    mLastStatusBarAppearanceRegions=
      AppearanceRegion{ bounds=[0,0][1080,2340]}
    mLastLetterboxDetails=
    mStatusBarBackgroundWindows=
      Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
    mTopIsFullscreen=false
    mForceShowNavigationBarEnabled=false mAllowLockscreenWhenOn=false
    mRemoteInsetsControllerControlsSystemBars=false
    mDecorInsetsInfo:
      ROTATION_0={nonDecorInsets=[0,136][0,126], configInsets=[0,136][0,126], nonDecorFrame=[0,136][1080,2214], configFrame=[0,136][1080,2214]}
      ROTATION_90={nonDecorInsets=[136,0][126,0], configInsets=[136,74][126,0], nonDecorFrame=[136,0][2214,1080], configFrame=[136,74][2214,1080]}
      ROTATION_180={nonDecorInsets=[0,0][0,262], configInsets=[0,74][0,262], nonDecorFrame=[0,0][1080,2078], configFrame=[0,74][1080,2078]}
      ROTATION_270={nonDecorInsets=[126,0][136,0], configInsets=[126,74][136,0], nonDecorFrame=[126,0][2204,1080], configFrame=[126,74][2204,1080]}
    SystemGestures:
      mDisplayCutoutTouchableRegionSize=32
      mSwipeStartThreshold=Rect(63, 168 - 63, 63)
      mSwipeDistanceThreshold=63
    Looper state:
      Looper (android.ui, tid 23) {b2b50e2}
        (Total messages: 0, polling=true, quitting=false)

  DisplayRotation
    mCurrentAppOrientation=SCREEN_ORIENTATION_NOSENSOR
    mLastOrientation=5
    mRotation=0 mDeferredRotationPauseCount=0
    mLandscapeRotation=ROTATION_90 mSeascapeRotation=ROTATION_270
    mPortraitRotation=ROTATION_0 mUpsideDownRotation=ROTATION_180
    mSupportAutoRotation=true
    WindowOrientationListener
      mEnabled=true
      mCurrentRotation=ROTATION_0
      mSensorType=null
      mSensor={Sensor name="Device Orientation", vendor="Google", version=1, type=27, maxRange=3.0, resolution=1.0, power=1.0, minDelay=0}
      mRate=2
      OrientationSensorJudge
        mDesiredRotation=ROTATION_0
        mProposedRotation=ROTATION_0
        mTouching=false
        mTouchEndedTimestampNanos=580610468931
        mLastRotationResolution=-1

    mCarDockRotation=-1 mDeskDockRotation=-1
    mUserRotationMode=USER_ROTATION_FREE mUserRotation=ROTATION_0 mCameraRotationMode=0 mAllowAllRotations=unknown
    mDemoHdmiRotation=ROTATION_90 mDemoHdmiRotationLock=false mUndockedHdmiRotation=-1
    mLidOpenRotation=-1
    mFixedToUserRotation=false

  InputConsumers:
    name=recents_animation_input_consumer pid=2961 user=UserHandle{0}

  WindowInsetsStateController
    InsetsState
      mDisplayFrame=Rect(0, 0 - 1080, 2340)
      mDisplayCutout=DisplayCutout{insets=Rect(0, 136 - 0, 0) waterfall=Insets{left=0, top=0, right=0, bottom=0} boundingRect={Bounds=[Rect(0, 0 - 0, 0), Rect(0, 0 - 145, 136), Rect(0, 0 - 0, 0), Rect(0, 0 - 0, 0)]} cutoutPathParserInfo={CutoutPathParserInfo{displayWidth=1080 displayHeight=2340 physicalDisplayWidth=1080 physicalDisplayHeight=2340 density={2.625} cutoutSpec={M 37,77 a 40,40 0 1 0 80,0 40,40 0 1 0 -80,0 Z @left} rotation={0} scale={1.0} physicalPixelDisplaySizeRatio={1.0}}}}
      mRoundedCorners=RoundedCorners{[RoundedCorner{position=TopLeft, radius=108, center=Point(108, 108)}, RoundedCorner{position=TopRight, radius=108, center=Point(972, 108)}, RoundedCorner{position=BottomRight, radius=108, center=Point(972, 2232)}, RoundedCorner{position=BottomLeft, radius=108, center=Point(108, 2232)}]}
      mRoundedCornerFrame=Rect(0, 0 - 0, 0)
      mPrivacyIndicatorBounds=PrivacyIndicatorBounds {static bounds=Rect(827, 0 - 1043, 136) rotation=0}
      mDisplayShape=DisplayShape{ spec=-786641078 displayWidth=1080 displayHeight=2340 physicalPixelDisplaySizeRatio=1.0 rotation=0 offsetX=0 offsetY=0 scale=1.0}
        InsetsSource id=d00d0000 type=statusBars frame=[0,0][1080,136] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=d00d0005 type=mandatorySystemGestures frame=[0,0][1080,168] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=d00d0006 type=tappableElement frame=[0,0][1080,136] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=e48b0001 type=navigationBars frame=[0,2214][1080,2340] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=e48b0004 type=systemGestures frame=[0,0][0,0] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=e48b0005 type=mandatorySystemGestures frame=[0,2214][1080,2340] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=e48b0006 type=tappableElement frame=[0,2214][1080,2340] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=e48b0024 type=systemGestures frame=[0,0][0,0] visible=true flags= insetsRoundedCornerFrame=false
        InsetsSource id=3 type=ime frame=[0,0][0,0] visible=false flags= insetsRoundedCornerFrame=false
        InsetsSource id=27 type=displayCutout frame=[0,0][1080,136] visible=true flags= insetsRoundedCornerFrame=false
    Control map:
      Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}:
        InsetsSourceControl: {d00d0000 mType=statusBars initiallyVisible mSurfacePosition=Point(0, 0) mInsetsHint=Insets{left=0, top=136, right=0, bottom=0}}
        InsetsSourceControl: {3 mType=ime mSurfacePosition=Point(120, 2214) mInsetsHint=Insets{left=0, top=0, right=0, bottom=0}}
        InsetsSourceControl: {e48b0001 mType=navigationBars initiallyVisible mSurfacePosition=Point(0, 2214) mInsetsHint=Insets{left=0, top=0, right=0, bottom=126}}
    InsetsSourceProviders:
      ImeInsetsSourceProvider
        mSource=InsetsSource id=3 type=ime frame=[0,0][0,0] visible=false flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(120, 2214 - 960, 2340)
        mControl=InsetsSourceControl mId=3 mType=ime mLeash=Surface(name=Surface(name=292b439 InputMethod)/@0x4ec702c - animation-leash of insets_animation)/@0x73deacf mInitiallyVisible=false mSurfacePosition=Point(120, 2214) mInsetsHint=Insets{left=0, top=0, right=0, bottom=0} mSkipAnimationOnce=false
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{292b439 u0 InputMethod}
        mAdapter=ControlAdapter mCapturedLeash=Surface(name=Surface(name=292b439 InputMethod)/@0x4ec702c - animation-leash of insets_animation)/@0x73deacf
        mControlTarget=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
        mImeShowing=false
      InsetsSourceProvider
        mSource=InsetsSource id=e48b0024 type=systemGestures frame=[0,0][0,0] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 0 - 0, 0)
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{6dc8727 u0 NavigationBar0}
      InsetsSourceProvider
        mSource=InsetsSource id=e48b0006 type=tappableElement frame=[0,2214][1080,2340] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 2214 - 1080, 2340)
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{6dc8727 u0 NavigationBar0}
      InsetsSourceProvider
        mSource=InsetsSource id=e48b0005 type=mandatorySystemGestures frame=[0,2214][1080,2340] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 2214 - 1080, 2340)
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{6dc8727 u0 NavigationBar0}
      InsetsSourceProvider
        mSource=InsetsSource id=e48b0004 type=systemGestures frame=[0,0][0,0] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 0 - 0, 0)
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{6dc8727 u0 NavigationBar0}
      InsetsSourceProvider
        mSource=InsetsSource id=e48b0001 type=navigationBars frame=[0,2214][1080,2340] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 2214 - 1080, 2340)
        mOverrideFrames={2011=Rect(0, 2214 - 1080, 2340)}
        mControl=InsetsSourceControl mId=e48b0001 mType=navigationBars mLeash=Surface(name=Surface(name=6dc8727 NavigationBar0)/@0xa4a85b0 - animation-leash of insets_animation)/@0xb5711ed mInitiallyVisible=true mSurfacePosition=Point(0, 2214) mInsetsHint=Insets{left=0, top=0, right=0, bottom=126} mSkipAnimationOnce=false
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{6dc8727 u0 NavigationBar0}
        mAdapter=ControlAdapter mCapturedLeash=Surface(name=Surface(name=6dc8727 NavigationBar0)/@0xa4a85b0 - animation-leash of insets_animation)/@0xb5711ed
        mControlTarget=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
      InsetsSourceProvider
        mSource=InsetsSource id=d00d0006 type=tappableElement frame=[0,0][1080,136] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 0 - 1080, 136)
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{32f3e94 u0 StatusBar}
      InsetsSourceProvider
        mSource=InsetsSource id=d00d0005 type=mandatorySystemGestures frame=[0,0][1080,168] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 0 - 1080, 168)
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{32f3e94 u0 StatusBar}
      InsetsSourceProvider
        mSource=InsetsSource id=d00d0000 type=statusBars frame=[0,0][1080,136] visible=true flags= insetsRoundedCornerFrame=false
        mSourceFrame=Rect(0, 0 - 1080, 136)
        mControl=InsetsSourceControl mId=d00d0000 mType=statusBars mLeash=Surface(name=Surface(name=32f3e94 StatusBar)/@0x42ad8e2 - animation-leash of insets_animation)/@0xc094792 mInitiallyVisible=true mSurfacePosition=Point(0, 0) mInsetsHint=Insets{left=0, top=136, right=0, bottom=0} mSkipAnimationOnce=false
        mIsLeashReadyForDispatching=true
        mWindowContainer=Window{32f3e94 u0 StatusBar}
        mAdapter=ControlAdapter mCapturedLeash=Surface(name=Surface(name=32f3e94 StatusBar)/@0x42ad8e2 - animation-leash of insets_animation)/@0xc094792
        mControlTarget=Window{5cb5743 u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}

  KeyguardController:
    mKeyguardShowing=false
    mAodShowing=false
    mKeyguardGoingAway=false
   KeyguardShowing=false AodShowing=false KeyguardGoingAway=false DismissalRequested=false  Occluded=false DismissingKeyguardActivity=null TurnScreenOnActivity=null at display=0
    mDismissalRequested=false

  LockTaskController:
    mLockTaskModeState=NONE
    mLockTaskModeTasks=
    mLockTaskPackages (userId:packages)=

  mCurTaskIdForUser={0=211}
  mUserRootTaskInFront={}
  mVisibilityTransactionDepth=0
  isHomeRecentsComponent=true
  mNoHistoryActivities=[]

  TaskOrganizerController:
      android.window.ITaskOrganizer$Stub$Proxy@46dddaa uid=10136:
        (fullscreen) Task{21a4759 #1 type=home}
        (fullscreen) Task{46e36e5 #2 type=undefined}
        (multi-window) Task{f47a3e0 #3 type=undefined}
        (multi-window) Task{bfea16a #4 type=undefined}

  VisibleActivityProcess:[ ProcessRecord{7863d74 2961:com.android.launcher3/u0a134}]
  NumNonAppVisibleWindowUidMap:[ 10136:5]
