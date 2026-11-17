package com.webcam.adb;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.ImageFormat;
import android.graphics.Rect;
import android.graphics.SurfaceTexture;
import android.graphics.YuvImage;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CameraMetadata;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.MeteringRectangle;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.Image;
import android.media.ImageReader;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaRecorder;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;
import android.util.Range;
import android.util.Size;
import android.view.Surface;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Foreground service.
 *  - TCP 8554: raw H.264 Annex-B (multiple clients, for ffmpeg / webcam.sh)
 *  - TCP 8555: raw PCM s16le 48 kHz mono microphone
 *  - HTTP 8080: web viewer (MJPEG) + remote control API
 * The camera runs only while somebody needs it (PC client, web client or on-screen preview).
 */
public class CamService extends Service {
    static final String TAG = "WebCamADB";
    static final int PORT_VIDEO = 8554, PORT_AUDIO = 8555, PORT_HTTP = 8556;
    static final int AUDIO_RATE = 48000;
    static final String ACTION_STOP = "com.webcam.adb.STOP";
    static final String CHANNEL = "webcam";

    static volatile CamService instance;
    static volatile String status = "Detenido";

    // ---- settings (SharedPreferences "cfg") ----
    volatile String facing = "back";
    volatile int width = 1280, height = 720, fps = 30, bitrate = 6_000_000;
    volatile boolean audioEnabled = true;
    volatile boolean micMuted = false;
    static final int PORT_DISCOVERY = 8557;

    // ---- live controls ----
    volatile float zoom = 1f;
    volatile boolean torch = false;
    volatile int exposure = 0;

    // ---- camera capabilities (valid while pipeline runs) ----
    volatile float minZoom = 1f, maxZoom = 1f;
    volatile int expMin = 0, expMax = 0;
    volatile boolean hasFlash = false;
    volatile Size curSize = null;
    volatile boolean cameraActive = false;

    // ---- stats ----
    volatile int statFps = 0;
    volatile long statKbps = 0;
    final AtomicInteger audioClients = new AtomicInteger();

    private volatile boolean running;
    private HandlerThread camThread, jpegThread;
    private Handler camHandler, jpegHandler;
    private final List<ServerSocket> servers = new ArrayList<>();
    private PowerManager.WakeLock wakeLock;
    private WifiManager.WifiLock wifiLock;

    // pipeline (camHandler thread only)
    private int gen = 0;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private CameraCharacteristics chars;
    private MediaCodec encoder;
    private Surface encSurface;
    private ImageReader jpegReader;
    private SurfaceTexture previewTexture;
    private Surface previewSurface;
    private boolean sessionHasPreview, sessionHasJpeg;
    private int sessionFailLevel = 0;
    private MeteringRectangle focusRect;
    private final Runnable focusReset = () -> { focusRect = null; applyRequest(); };
    private final Runnable idleStop = () -> { if (!wanted()) stopPipeline(); };

    private volatile byte[] codecConfig;
    private volatile byte[] latestJpeg;
    private final Object jpegLock = new Object();
    private long lastJpegAt = 0;

    final List<VideoClient> videoClients = new CopyOnWriteArrayList<>();
    final List<Object> webClients = new CopyOnWriteArrayList<>();

    // =====================================================================
    // Service lifecycle
    // =====================================================================

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        loadSettings();
        camThread = new HandlerThread("cam");
        camThread.start();
        camHandler = new Handler(camThread.getLooper());
        jpegThread = new HandlerThread("jpeg");
        jpegThread.start();
        jpegHandler = new Handler(jpegThread.getLooper());
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "webcam:stream");
        WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
        if (wm != null) {
            wifiLock = wm.createWifiLock(Build.VERSION.SDK_INT >= 29
                    ? WifiManager.WIFI_MODE_FULL_LOW_LATENCY : WifiManager.WIFI_MODE_FULL_HIGH_PERF, "webcam:wifi");
        }
        instance = this;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        startForegroundCompat();
        if (Updater.isBlocked(this)) {
            // Security: a mandatory update is pending; never expose camera/mic from a vulnerable build.
            status = "Actualización obligatoria pendiente";
            stopSelf();
            return START_NOT_STICKY;
        }
        if (!running) {
            running = true;
            startServer(PORT_VIDEO, this::onVideoClient);
            startServer(PORT_AUDIO, this::onAudioClient);
            startServer(PORT_HTTP, this::onHttpClient);
            new Thread(this::beaconLoop, "beacon").start();
            status = "En espera de conexión";
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        instance = null;
        for (ServerSocket s : servers) try { s.close(); } catch (IOException ignored) { }
        for (VideoClient c : videoClients) c.close();
        CountDownLatch l = new CountDownLatch(1);
        camHandler.post(() -> { stopPipeline(); l.countDown(); });
        try { l.await(2, TimeUnit.SECONDS); } catch (InterruptedException ignored) { }
        camThread.quitSafely();
        jpegThread.quitSafely();
        updateLocks();
        if (wakeLock.isHeld()) wakeLock.release();
        if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        status = "Detenido";
        super.onDestroy();
    }

    private void startForegroundCompat() {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, "WebCam", NotificationManager.IMPORTANCE_LOW));
        }
        PendingIntent pi = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent ps = PendingIntent.getService(this, 1,
                new Intent(this, CamService.class).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        Notification n = b.setContentTitle("PocketLens activa")
                .setContentText("Vídeo " + PORT_VIDEO + " · Audio " + PORT_AUDIO + " · Web " + PORT_HTTP)
                .setSmallIcon(R.drawable.ic_videocam)
                .setContentIntent(pi)
                .addAction(new Notification.Action.Builder(null, "Detener", ps).build())
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 29) {
            int type = ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA;
            if (hasMicPermission()) type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE;
            startForeground(1, n, type);
        } else {
            startForeground(1, n);
        }
    }

    boolean hasMicPermission() {
        return checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }

    // =====================================================================
    // Settings & public controls (called from UI / HTTP, any thread)
    // =====================================================================

    void loadSettings() {
        SharedPreferences p = getSharedPreferences("cfg", MODE_PRIVATE);
        facing = p.getString("camera", "back");
        String[] wh = p.getString("res", "1280x720").split("x");
        width = Integer.parseInt(wh[0]);
        height = Integer.parseInt(wh[1]);
        fps = Integer.parseInt(p.getString("fps", "30"));
        bitrate = Integer.parseInt(p.getString("bitrate", "6")) * 1_000_000;
        audioEnabled = p.getBoolean("audio", true);
    }

    /** Re-read settings and restart the camera pipeline if it's running. */
    void reloadSettings() {
        camHandler.post(() -> {
            loadSettings();
            zoom = 1f;
            torch = false;
            exposure = 0;
            if (camera != null) { stopPipeline(); evaluate(); }
        });
    }

    void switchCamera() {
        String next = "front".equals(facing) ? "back" : "front";
        getSharedPreferences("cfg", MODE_PRIVATE).edit().putString("camera", next).apply();
        reloadSettings();
    }

    void setZoom(float z) {
        zoom = Math.max(minZoom, Math.min(maxZoom, z));
        camHandler.post(this::applyRequest);
    }

    void setMicMuted(boolean m) { micMuted = m; }

    void setTorch(boolean on) {
        torch = on;
        camHandler.post(this::applyRequest);
    }

    void setExposure(int e) {
        exposure = Math.max(expMin, Math.min(expMax, e));
        camHandler.post(this::applyRequest);
    }

    /** nx, ny in [0,1] relative to the streamed image. */
    void focusAt(float nx, float ny) {
        camHandler.post(() -> {
            if (chars == null || session == null) return;
            Integer maxAf = chars.get(CameraCharacteristics.CONTROL_MAX_REGIONS_AF);
            if (maxAf == null || maxAf < 1) return;
            Rect a = chars.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE);
            int half = Math.max(a.width(), a.height()) / 20;
            int x = (int) (a.left + nx * a.width()), y = (int) (a.top + ny * a.height());
            int l = Math.max(a.left, x - half), t = Math.max(a.top, y - half);
            int r = Math.min(a.right - 1, x + half), b = Math.min(a.bottom - 1, y + half);
            focusRect = new MeteringRectangle(l, t, r - l, b - t, MeteringRectangle.METERING_WEIGHT_MAX - 1);
            applyRequest();
            try {
                CaptureRequest.Builder tb = buildRequest();
                tb.set(CaptureRequest.CONTROL_AF_TRIGGER, CameraMetadata.CONTROL_AF_TRIGGER_START);
                session.capture(tb.build(), null, camHandler);
            } catch (Exception e) {
                Log.w(TAG, "focus", e);
            }
            camHandler.removeCallbacks(focusReset);
            camHandler.postDelayed(focusReset, 6000);
        });
    }

    /** Attach (or detach with null) the on-screen preview. Blocks briefly so the surface isn't torn down mid-use. */
    void setPreview(SurfaceTexture st) {
        CountDownLatch l = new CountDownLatch(1);
        camHandler.post(() -> {
            previewTexture = st;
            evaluate();
            l.countDown();
        });
        try { l.await(1, TimeUnit.SECONDS); } catch (InterruptedException ignored) { }
    }

    int clientCount() { return videoClients.size(); }
    int webCount() { return webClients.size(); }

    // =====================================================================
    // Pipeline management (camHandler thread)
    // =====================================================================

    private boolean wanted() {
        return running && (!videoClients.isEmpty() || !webClients.isEmpty() || previewTexture != null);
    }

    private void postEvaluate() { camHandler.post(this::evaluate); }

    private void evaluate() {
        updateLocks();
        if (wanted()) {
            camHandler.removeCallbacks(idleStop);
            if (camera == null && encoder == null) {
                startPipeline();
            } else if (camera != null) {
                boolean wantPreview = previewTexture != null, wantJpeg = !webClients.isEmpty();
                if (wantPreview != sessionHasPreview || wantJpeg != sessionHasJpeg) {
                    sessionFailLevel = 0;
                    createSession();
                }
            }
        } else if (camera != null) {
            camHandler.removeCallbacks(idleStop);
            camHandler.postDelayed(idleStop, 3000);
        }
        if (running) {
            status = cameraActive
                    ? (videoClients.isEmpty() && webClients.isEmpty() ? "Vista previa" : "EN VIVO")
                    : "En espera de conexión";
        }
    }

    private void updateLocks() {
        boolean need = running && (!videoClients.isEmpty() || !webClients.isEmpty() || audioClients.get() > 0);
        if (need && !wakeLock.isHeld()) {
            wakeLock.acquire();
            if (wifiLock != null) wifiLock.acquire();
        } else if (!need && wakeLock.isHeld()) {
            wakeLock.release();
            if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        }
    }

    private String findCameraId(CameraManager cm) throws CameraAccessException {
        int want = "front".equals(facing) ? CameraCharacteristics.LENS_FACING_FRONT : CameraCharacteristics.LENS_FACING_BACK;
        String fallback = null;
        for (String id : cm.getCameraIdList()) {
            Integer f = cm.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING);
            if (fallback == null) fallback = id;
            if (f != null && f == want) return id;
        }
        if (fallback == null) throw new CameraAccessException(CameraAccessException.CAMERA_ERROR, "Sin cámaras");
        return fallback;
    }

    private static Size chooseSize(Size[] sizes, int w, int h) {
        if (sizes == null || sizes.length == 0) return new Size(w, h);
        Size best = null;
        double wantRatio = (double) w / h, bestScore = Double.MAX_VALUE;
        long wantArea = (long) w * h;
        for (Size sz : sizes) {
            if (sz.getWidth() == w && sz.getHeight() == h) return sz;
            double ratioDiff = Math.abs((double) sz.getWidth() / sz.getHeight() - wantRatio);
            double areaDiff = Math.abs(Math.log((double) sz.getWidth() * sz.getHeight() / wantArea));
            double score = ratioDiff * 10 + areaDiff;
            if (score < bestScore) { bestScore = score; best = sz; }
        }
        return best;
    }

    private Range<Integer> chooseFpsRange() {
        Range<Integer>[] ranges = chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES);
        if (ranges == null || ranges.length == 0) return null;
        Range<Integer> best = null;
        for (Range<Integer> r : ranges) {
            if (r.getUpper() == fps && r.getLower() == fps) return r;
            if (r.getUpper() == fps && (best == null || r.getLower() > best.getLower())) best = r;
        }
        if (best != null) return best;
        for (Range<Integer> r : ranges) {
            if (best == null || Math.abs(r.getUpper() - fps) < Math.abs(best.getUpper() - fps)) best = r;
        }
        return best;
    }

    private MediaCodec createEncoder(Size size) throws IOException {
        MediaCodec enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
        MediaFormat fmt = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, size.getWidth(), size.getHeight());
        fmt.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        fmt.setInteger(MediaFormat.KEY_BIT_RATE, bitrate);
        fmt.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
        fmt.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
        fmt.setLong(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER, 100_000);
        fmt.setInteger(MediaFormat.KEY_PRIORITY, 0);
        if (Build.VERSION.SDK_INT >= 30) fmt.setInteger(MediaFormat.KEY_LOW_LATENCY, 1);
        try {
            enc.configure(fmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        } catch (Exception e) {
            enc.reset();
            MediaFormat f2 = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, size.getWidth(), size.getHeight());
            f2.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
            f2.setInteger(MediaFormat.KEY_BIT_RATE, bitrate);
            f2.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
            f2.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
            enc.configure(f2, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        }
        return enc;
    }

    @SuppressWarnings("MissingPermission")
    private void startPipeline() {
        final int myGen = ++gen;
        try {
            CameraManager cm = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
            String id = findCameraId(cm);
            chars = cm.getCameraCharacteristics(id);
            StreamConfigurationMap map = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            Size size = chooseSize(map.getOutputSizes(MediaCodec.class), width, height);
            readCapabilities();

            encoder = createEncoder(size);
            encSurface = encoder.createInputSurface();
            encoder.start();
            curSize = size;
            final MediaCodec enc = encoder;
            new Thread(() -> drainLoop(enc), "drain").start();

            Size js = chooseSize(map.getOutputSizes(ImageFormat.YUV_420_888), 640, 640 * size.getHeight() / size.getWidth());
            jpegReader = ImageReader.newInstance(js.getWidth(), js.getHeight(), ImageFormat.YUV_420_888, 3);
            jpegReader.setOnImageAvailableListener(this::onJpegImage, jpegHandler);

            cm.openCamera(id, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice c) {
                    if (myGen != gen) { c.close(); return; }
                    camera = c;
                    sessionFailLevel = 0;
                    createSession();
                }
                @Override public void onDisconnected(CameraDevice c) { onCameraFailure(c, myGen, "cámara desconectada (¿otra app la usa?)"); }
                @Override public void onError(CameraDevice c, int e) { onCameraFailure(c, myGen, "error de cámara " + e); }
            }, camHandler);
        } catch (Exception e) {
            Log.e(TAG, "startPipeline", e);
            status = "Error: " + e.getMessage();
            stopPipeline();
            camHandler.postDelayed(this::evaluate, 2000);
        }
    }

    private void onCameraFailure(CameraDevice c, int myGen, String msg) {
        c.close();
        if (myGen != gen) return;
        camera = null;
        Log.w(TAG, msg);
        stopPipeline();
        status = msg;
        camHandler.postDelayed(this::evaluate, 1500);
    }

    private void readCapabilities() {
        Boolean flash = chars.get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
        hasFlash = flash != null && flash;
        Range<Integer> er = chars.get(CameraCharacteristics.CONTROL_AE_COMPENSATION_RANGE);
        expMin = er != null ? er.getLower() : 0;
        expMax = er != null ? er.getUpper() : 0;
        if (Build.VERSION.SDK_INT >= 30 && chars.get(CameraCharacteristics.CONTROL_ZOOM_RATIO_RANGE) != null) {
            Range<Float> zr = chars.get(CameraCharacteristics.CONTROL_ZOOM_RATIO_RANGE);
            minZoom = Math.max(1f, zr.getLower());
            maxZoom = zr.getUpper();
        } else {
            Float mz = chars.get(CameraCharacteristics.SCALER_AVAILABLE_MAX_DIGITAL_ZOOM);
            minZoom = 1f;
            maxZoom = mz != null ? mz : 1f;
        }
        zoom = Math.max(minZoom, Math.min(maxZoom, zoom));
        exposure = Math.max(expMin, Math.min(expMax, exposure));
    }

    /** sessionFailLevel: 0 = all outputs, 1 = drop jpeg if PC clients else preview, 2 = encoder only */
    private void createSession() {
        if (camera == null) return;
        final int myGen = gen;
        session = null;
        boolean wantPreview = previewTexture != null, wantJpeg = !webClients.isEmpty();
        boolean usePreview = wantPreview, useJpeg = wantJpeg;
        if (sessionFailLevel == 1 && wantPreview && wantJpeg) {
            if (videoClients.isEmpty()) usePreview = false; else useJpeg = false;
        } else if (sessionFailLevel >= 2) {
            usePreview = false;
            useJpeg = false;
        }
        List<Surface> targets = new ArrayList<>();
        targets.add(encSurface);
        if (previewSurface != null) { previewSurface.release(); previewSurface = null; }
        if (usePreview) {
            previewTexture.setDefaultBufferSize(curSize.getWidth(), curSize.getHeight());
            previewSurface = new Surface(previewTexture);
            targets.add(previewSurface);
        }
        if (useJpeg) targets.add(jpegReader.getSurface());
        sessionHasPreview = wantPreview;
        sessionHasJpeg = wantJpeg;
        final boolean fp = usePreview, fj = useJpeg;
        try {
            camera.createCaptureSession(targets, new CameraCaptureSession.StateCallback() {
                @Override public void onConfigured(CameraCaptureSession s) {
                    if (myGen != gen) { s.close(); return; }
                    session = s;
                    activeTargets = new boolean[]{fp, fj};
                    cameraActive = true;
                    applyRequest();
                    evaluate();
                }
                @Override public void onConfigureFailed(CameraCaptureSession s) {
                    if (myGen != gen) return;
                    Log.w(TAG, "session config failed at level " + sessionFailLevel);
                    if (sessionFailLevel < 2) {
                        sessionFailLevel++;
                        createSession();
                    } else {
                        status = "No se pudo configurar la cámara";
                    }
                }
            }, camHandler);
        } catch (Exception e) {
            Log.e(TAG, "createSession", e);
            onCameraFailure(camera, myGen, "error de sesión: " + e.getMessage());
        }
    }

    private boolean[] activeTargets = {false, false};

    private CaptureRequest.Builder buildRequest() throws CameraAccessException {
        CaptureRequest.Builder b = camera.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);
        b.addTarget(encSurface);
        if (activeTargets[0] && previewSurface != null) b.addTarget(previewSurface);
        if (activeTargets[1]) b.addTarget(jpegReader.getSurface());
        b.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
        Range<Integer> fr = chooseFpsRange();
        if (fr != null) b.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, fr);

        int[] afModes = chars.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES);
        boolean hasCont = false, hasAuto = false;
        if (afModes != null) for (int m : afModes) {
            if (m == CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO) hasCont = true;
            if (m == CaptureRequest.CONTROL_AF_MODE_AUTO) hasAuto = true;
        }
        if (focusRect != null && hasAuto) {
            b.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_AUTO);
            b.set(CaptureRequest.CONTROL_AF_REGIONS, new MeteringRectangle[]{focusRect});
            Integer maxAe = chars.get(CameraCharacteristics.CONTROL_MAX_REGIONS_AE);
            if (maxAe != null && maxAe > 0) b.set(CaptureRequest.CONTROL_AE_REGIONS, new MeteringRectangle[]{focusRect});
        } else if (hasCont) {
            b.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO);
        }

        b.set(CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION, exposure);
        if (torch && hasFlash) {
            b.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON);
            b.set(CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_TORCH);
        } else {
            b.set(CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_OFF);
        }

        if (Build.VERSION.SDK_INT >= 30 && chars.get(CameraCharacteristics.CONTROL_ZOOM_RATIO_RANGE) != null) {
            b.set(CaptureRequest.CONTROL_ZOOM_RATIO, zoom);
        } else if (zoom > 1f) {
            Rect a = chars.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE);
            int cw = (int) (a.width() / zoom), ch = (int) (a.height() / zoom);
            int cx = a.centerX(), cy = a.centerY();
            b.set(CaptureRequest.SCALER_CROP_REGION, new Rect(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2));
        }
        return b;
    }

    private void applyRequest() {
        if (session == null || camera == null) return;
        try {
            session.setRepeatingRequest(buildRequest().build(), null, camHandler);
        } catch (Exception e) {
            Log.w(TAG, "applyRequest", e);
        }
    }

    private void stopPipeline() {
        gen++;
        cameraActive = false;
        camHandler.removeCallbacks(focusReset);
        focusRect = null;
        try { if (session != null) session.close(); } catch (Exception ignored) { }
        session = null;
        try { if (camera != null) camera.close(); } catch (Exception ignored) { }
        camera = null;
        MediaCodec enc = encoder;
        encoder = null;
        if (enc != null) {
            try { enc.stop(); } catch (Exception ignored) { }
            try { enc.release(); } catch (Exception ignored) { }
        }
        if (encSurface != null) encSurface.release();
        encSurface = null;
        if (previewSurface != null) previewSurface.release();
        previewSurface = null;
        if (jpegReader != null) jpegReader.close();
        jpegReader = null;
        sessionHasPreview = sessionHasJpeg = false;
        activeTargets = new boolean[]{false, false};
        codecConfig = null;
        statFps = 0;
        statKbps = 0;
        if (running) status = "En espera de conexión";
    }

    // =====================================================================
    // Encoder output
    // =====================================================================

    private void drainLoop(MediaCodec enc) {
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        int frames = 0;
        long bytes = 0, t0 = System.nanoTime();
        try {
            while (true) {
                int idx = enc.dequeueOutputBuffer(info, 100_000);
                long now = System.nanoTime();
                if (now - t0 >= 1_000_000_000L) {
                    double s = (now - t0) / 1e9;
                    statFps = (int) Math.round(frames / s);
                    statKbps = (long) (bytes * 8 / 1000 / s);
                    frames = 0;
                    bytes = 0;
                    t0 = now;
                }
                if (idx < 0) {
                    if (encoder != enc) break;
                    continue;
                }
                ByteBuffer bb = enc.getOutputBuffer(idx);
                byte[] data = null;
                if (bb != null && info.size > 0) {
                    data = new byte[info.size];
                    bb.position(info.offset);
                    bb.get(data);
                }
                int fl = info.flags;
                enc.releaseOutputBuffer(idx, false);
                if (data != null) {
                    if ((fl & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                        codecConfig = data;
                        for (VideoClient c : videoClients) c.offerConfig(data);
                    } else {
                        frames++;
                        bytes += data.length;
                        boolean key = (fl & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0;
                        for (VideoClient c : videoClients) c.offerFrame(data, key);
                    }
                }
                if ((fl & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) break;
            }
        } catch (Exception e) {
            // encoder released
        }
    }

    void requestKeyframe() {
        MediaCodec enc = encoder;
        if (enc == null) return;
        try {
            Bundle b = new Bundle();
            b.putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0);
            enc.setParameters(b);
        } catch (Exception ignored) { }
    }

    // =====================================================================
    // Servers
    // =====================================================================

    interface ClientHandler { void handle(Socket s) throws Exception; }

    private void startServer(int port, ClientHandler h) {
        new Thread(() -> {
            ServerSocket ss;
            try {
                ss = new ServerSocket();
                ss.setReuseAddress(true);
                ss.bind(new InetSocketAddress(port));
            } catch (IOException e) {
                Log.e(TAG, "bind " + port, e);
                status = "Error abriendo puerto " + port;
                return;
            }
            synchronized (servers) { servers.add(ss); }
            while (running) {
                try {
                    Socket s = ss.accept();
                    new Thread(() -> {
                        try { h.handle(s); } catch (Exception e) { Log.d(TAG, "client " + port + ": " + e); }
                        finally { try { s.close(); } catch (IOException ignored) { } }
                    }, "client-" + port).start();
                } catch (IOException e) {
                    break;
                }
            }
        }, "server-" + port).start();
    }

    /** UDP broadcast every 2 s so desktop clients can discover the phone on the LAN. */
    private void beaconLoop() {
        try (java.net.DatagramSocket ds = new java.net.DatagramSocket()) {
            ds.setBroadcast(true);
            java.net.InetAddress bcast = java.net.InetAddress.getByName("255.255.255.255");
            while (running) {
                String msg = String.format(Locale.US,
                        "{\"app\":\"webcam-adb\",\"name\":\"%s\",\"video\":%d,\"audio\":%d,\"http\":%d,\"live\":%b}",
                        Build.MODEL.replace("\"", "'"), PORT_VIDEO, PORT_AUDIO, PORT_HTTP, !videoClients.isEmpty());
                byte[] b = msg.getBytes(StandardCharsets.UTF_8);
                try { ds.send(new java.net.DatagramPacket(b, b.length, bcast, PORT_DISCOVERY)); } catch (IOException ignored) { }
                Thread.sleep(2000);
            }
        } catch (Exception e) {
            Log.w(TAG, "beacon", e);
        }
    }

    // ---- H.264 clients ----

    final class VideoClient {
        final Socket socket;
        final ArrayBlockingQueue<byte[]> q = new ArrayBlockingQueue<>(120);
        volatile boolean needKey = true, closed = false;

        VideoClient(Socket s) { socket = s; }

        void offerConfig(byte[] d) {
            q.clear();
            q.offer(d);
            needKey = true;
        }

        void offerFrame(byte[] d, boolean key) {
            if (needKey) {
                if (!key) return;
                needKey = false;
            }
            if (!q.offer(d)) { // client too slow: drop and resync on next keyframe
                q.clear();
                byte[] cfg = codecConfig;
                if (cfg != null) q.offer(cfg);
                needKey = true;
                requestKeyframe();
            }
        }

        void close() {
            closed = true;
            try { socket.close(); } catch (IOException ignored) { }
        }

        void run() throws Exception {
            socket.setTcpNoDelay(true);
            socket.setSendBufferSize(512 * 1024);
            OutputStream out = socket.getOutputStream();
            byte[] cfg = codecConfig;
            if (cfg != null) q.offer(cfg);
            requestKeyframe();
            while (!closed && running) {
                byte[] d = q.poll(500, TimeUnit.MILLISECONDS);
                if (d != null) out.write(d);
            }
        }
    }

    private void onVideoClient(Socket s) throws Exception {
        VideoClient c = new VideoClient(s);
        videoClients.add(c);
        postEvaluate();
        try {
            c.run();
        } finally {
            videoClients.remove(c);
            postEvaluate();
        }
    }

    // ---- audio ----

    @SuppressWarnings("MissingPermission")
    private void onAudioClient(Socket s) throws Exception {
        if (!audioEnabled || !hasMicPermission()) return;
        if (audioClients.get() > 0) return; // one at a time
        int minBuf = AudioRecord.getMinBufferSize(AUDIO_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        AudioRecord rec = new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, AUDIO_RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(minBuf, AUDIO_RATE / 5 * 2));
        if (rec.getState() != AudioRecord.STATE_INITIALIZED) {
            rec.release();
            return;
        }
        audioClients.incrementAndGet();
        postEvaluate();
        try {
            s.setTcpNoDelay(true);
            OutputStream out = s.getOutputStream();
            byte[] buf = new byte[AUDIO_RATE / 50 * 2]; // 20 ms
            rec.startRecording();
            while (running && audioEnabled) {
                int n = rec.read(buf, 0, buf.length);
                if (n < 0) break;
                if (micMuted) java.util.Arrays.fill(buf, 0, n, (byte) 0);
                if (n > 0) out.write(buf, 0, n);
            }
        } finally {
            try { rec.stop(); } catch (Exception ignored) { }
            rec.release();
            audioClients.decrementAndGet();
            postEvaluate();
        }
    }

    // ---- MJPEG for web clients ----

    private void onJpegImage(ImageReader r) {
        Image img;
        try { img = r.acquireLatestImage(); } catch (Exception e) { return; }
        if (img == null) return;
        try {
            long now = System.currentTimeMillis();
            if (webClients.isEmpty() || now - lastJpegAt < 66) return; // ~15 fps
            lastJpegAt = now;
            int w = img.getWidth(), h = img.getHeight();
            byte[] nv21 = yuvToNv21(img);
            ByteArrayOutputStream bos = new ByteArrayOutputStream(w * h / 4);
            new YuvImage(nv21, ImageFormat.NV21, w, h, null).compressToJpeg(new Rect(0, 0, w, h), 75, bos);
            synchronized (jpegLock) {
                latestJpeg = bos.toByteArray();
                jpegLock.notifyAll();
            }
        } catch (Exception e) {
            Log.w(TAG, "jpeg", e);
        } finally {
            img.close();
        }
    }

    private static byte[] yuvToNv21(Image img) {
        int w = img.getWidth(), h = img.getHeight();
        byte[] out = new byte[w * h * 3 / 2];
        Image.Plane[] p = img.getPlanes();
        ByteBuffer y = p[0].getBuffer();
        int yRow = p[0].getRowStride();
        for (int r = 0; r < h; r++) {
            y.position(r * yRow);
            y.get(out, r * w, w);
        }
        ByteBuffer u = p[1].getBuffer(), v = p[2].getBuffer();
        int uvRow = p[1].getRowStride(), uvPix = p[1].getPixelStride();
        int o = w * h;
        for (int r = 0; r < h / 2; r++) {
            int base = r * uvRow;
            for (int c = 0; c < w / 2; c++) {
                int i = base + c * uvPix;
                out[o++] = v.get(i);
                out[o++] = u.get(i);
            }
        }
        return out;
    }

    private byte[] waitJpeg(byte[] previous, long timeoutMs) throws InterruptedException {
        long end = System.currentTimeMillis() + timeoutMs;
        synchronized (jpegLock) {
            while (latestJpeg == previous || latestJpeg == null) {
                long left = end - System.currentTimeMillis();
                if (left <= 0 || !running) return null;
                jpegLock.wait(left);
            }
            return latestJpeg;
        }
    }

    // ---- HTTP ----

    private void onHttpClient(Socket s) throws Exception {
        s.setSoTimeout(10_000);
        BufferedReader in = new BufferedReader(new InputStreamReader(s.getInputStream(), StandardCharsets.ISO_8859_1));
        String line = in.readLine();
        if (line == null) return;
        String hdr;
        while ((hdr = in.readLine()) != null && !hdr.isEmpty()) { /* skip headers */ }
        String[] parts = line.split(" ");
        if (parts.length < 2) return;
        String target = parts[1];
        String path = target, query = "";
        int qi = target.indexOf('?');
        if (qi >= 0) { path = target.substring(0, qi); query = target.substring(qi + 1); }
        OutputStream out = s.getOutputStream();
        s.setSoTimeout(0);

        switch (path) {
            case "/":
            case "/index.html":
                respond(out, 200, "text/html; charset=utf-8", WebPage.HTML.getBytes(StandardCharsets.UTF_8));
                return;
            case "/video":
                serveMjpeg(s, out);
                return;
            case "/snapshot.jpg":
                serveSnapshot(out);
                return;
            case "/api/status":
                break;
            case "/api/torch":
                setTorch(!torch);
                break;
            case "/api/switch":
                switchCamera();
                break;
            case "/api/zoom":
                setZoom(parseFloat(param(query, "v"), zoom));
                break;
            case "/api/exposure":
                setExposure((int) parseFloat(param(query, "v"), exposure));
                break;
            case "/api/mic":
                micMuted = !micMuted;
                break;
            case "/api/config":
                applyConfig(query);
                break;
            case "/api/focus":
                focusAt(parseFloat(param(query, "x"), .5f), parseFloat(param(query, "y"), .5f));
                break;
            default:
                respond(out, 404, "text/plain", "404".getBytes());
                return;
        }
        respond(out, 200, "application/json", statusJson().getBytes(StandardCharsets.UTF_8));
    }

    /** /api/config?camera=back&res=1280x720&fps=30&bitrate=6&audio=1 — only changed values restart the camera */
    private void applyConfig(String query) {
        SharedPreferences p = getSharedPreferences("cfg", MODE_PRIVATE);
        SharedPreferences.Editor ed = p.edit();
        boolean changed = false;
        String[][] keys = {{"camera", "back"}, {"res", "1280x720"}, {"fps", "30"}, {"bitrate", "6"}};
        for (String[] k : keys) {
            String v = param(query, k[0]);
            if (v == null) continue;
            if (k[0].equals("camera") && !v.equals("front") && !v.equals("back")) continue;
            if (k[0].equals("res") && !v.matches("\\d{2,5}x\\d{2,5}")) continue;
            if ((k[0].equals("fps") || k[0].equals("bitrate")) && !v.matches("\\d{1,3}")) continue;
            if (!v.equals(p.getString(k[0], k[1]))) { ed.putString(k[0], v); changed = true; }
        }
        String a = param(query, "audio");
        if (a != null) {
            boolean on = a.equals("1") || a.equals("true");
            if (on != p.getBoolean("audio", true)) { ed.putBoolean("audio", on); audioEnabled = on; }
        }
        ed.commit();
        if (changed) reloadSettings();
    }

    private static String param(String query, String name) {
        for (String kv : query.split("&")) {
            int e = kv.indexOf('=');
            if (e > 0 && kv.substring(0, e).equals(name)) {
                try { return URLDecoder.decode(kv.substring(e + 1), "UTF-8"); } catch (Exception ignored) { }
            }
        }
        return null;
    }

    private static float parseFloat(String s, float def) {
        try { return s == null ? def : Float.parseFloat(s); } catch (NumberFormatException e) { return def; }
    }

    String statusJson() {
        Size sz = curSize;
        return String.format(Locale.US,
                "{\"status\":\"%s\",\"camera\":\"%s\",\"width\":%d,\"height\":%d,\"fps\":%d,\"kbps\":%d," +
                        "\"zoom\":%.2f,\"minZoom\":%.2f,\"maxZoom\":%.2f,\"torch\":%b,\"hasFlash\":%b," +
                        "\"exposure\":%d,\"expMin\":%d,\"expMax\":%d,\"clients\":%d,\"web\":%d,\"audio\":%d," +
                        "\"muted\":%b,\"audioEnabled\":%b,\"model\":\"%s\",\"version\":\"%s\"}",
                status.replace("\"", "'"), facing, sz != null ? sz.getWidth() : width, sz != null ? sz.getHeight() : height,
                statFps, statKbps, zoom, minZoom, maxZoom, torch, hasFlash, exposure, expMin, expMax,
                videoClients.size(), webClients.size(), audioClients.get(),
                micMuted, audioEnabled, Build.MODEL.replace("\"", "'"), BuildInfo.VERSION);
    }

    private static void respond(OutputStream out, int code, String type, byte[] body) throws IOException {
        String h = "HTTP/1.0 " + code + (code == 200 ? " OK" : " Error") + "\r\nContent-Type: " + type +
                "\r\nContent-Length: " + body.length + "\r\nCache-Control: no-cache\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n";
        out.write(h.getBytes(StandardCharsets.ISO_8859_1));
        out.write(body);
        out.flush();
    }

    private void serveSnapshot(OutputStream out) throws Exception {
        Object token = new Object();
        webClients.add(token);
        postEvaluate();
        try {
            byte[] j = waitJpeg(null, 5000);
            if (j == null) respond(out, 503, "text/plain", "sin imagen".getBytes());
            else respond(out, 200, "image/jpeg", j);
        } finally {
            webClients.remove(token);
            postEvaluate();
        }
    }

    private void serveMjpeg(Socket s, OutputStream out) throws Exception {
        Object token = new Object();
        webClients.add(token);
        postEvaluate();
        try {
            s.setTcpNoDelay(true);
            out.write(("HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n" +
                    "Cache-Control: no-cache\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
            byte[] last = null;
            while (running) {
                byte[] j = waitJpeg(last, 3000);
                if (j == null) continue;
                last = j;
                out.write(("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + j.length + "\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
                out.write(j);
                out.write("\r\n".getBytes(StandardCharsets.ISO_8859_1));
                out.flush();
            }
        } finally {
            webClients.remove(token);
            postEvaluate();
        }
    }
}
