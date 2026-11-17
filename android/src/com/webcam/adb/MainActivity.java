package com.webcam.adb;

import android.Manifest;
import android.app.Activity;
import android.app.Dialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Matrix;
import android.graphics.RectF;
import android.graphics.SurfaceTexture;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.util.Size;
import android.view.GestureDetector;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity implements TextureView.SurfaceTextureListener {
    // ---- palette ----
    static final int BG = 0xFF0B0D10, SURFACE = 0xE6141920, SURFACE_2 = 0xFF1C222B, STROKE = 0x1FFFFFFF;
    static final int TEXT = 0xFFF1F3F5, TEXT_2 = 0xFFA3ABB5, TEXT_3 = 0xFF6B737D;
    static final int ACCENT = 0xFF22C55E, ACCENT_DARK = 0xFF16A34A, LIVE = 0xFFEF4444, WARN = 0xFFF59E0B;
    private static final int MATCH = ViewGroup.LayoutParams.MATCH_PARENT, WRAP = ViewGroup.LayoutParams.WRAP_CONTENT;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private FrameLayout root, previewBox;
    private TextureView texture;
    private View hud, dimOverlay, emptyState, statusDot;
    private Updater.Release pendingUpdate;
    private TextView tvUpdate;
    private TextView tvStatus, tvStats, tvIp, tvWeb, tvPc, tvWebClients, tvMic, tvZoomBig, tvExp, tvEmpty, dimText;
    private LinearLayout statusPill, expBar;
    private ImageView btTorch, btMic;
    private SeekBar sbExp;
    private final List<TextView> zoomPresets = new ArrayList<>();
    private boolean surfaceReady, previewAttached, resumed, dimmed, hudHidden, userTouchingExp;
    private Size lastSize;
    private ScaleGestureDetector scaleDetector;
    private GestureDetector gestureDetector;
    private final Runnable hideExp = () -> fade(expBar, false);
    private final Runnable hideZoomBig = () -> fade(tvZoomBig, false);

    // =====================================================================
    // Lifecycle
    // =====================================================================

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window w = getWindow();
        w.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        w.setStatusBarColor(Color.TRANSPARENT);
        w.setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= 28) {
            WindowManager.LayoutParams lp = w.getAttributes();
            lp.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            w.setAttributes(lp);
        }
        buildUi();
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    /** Extras from webcam.sh: camera, width, height, fps, bitrate(bps), audio, stop */
    private void handleIntent(Intent intent) {
        if (intent == null) return;
        if (Updater.ACTION_INSTALL_STATUS.equals(intent.getAction())) {
            handleInstallStatus(intent);
            return;
        }
        if (intent.getBooleanExtra("stop", false)) {
            stopService(new Intent(this, CamService.class));
            finish();
            return;
        }
        Bundle e = intent.getExtras();
        if (e == null) return;
        SharedPreferences p = prefs();
        SharedPreferences.Editor ed = p.edit();
        boolean changed = false;
        if (e.containsKey("camera")) changed |= putIfChanged(p, ed, "camera", e.getString("camera"));
        if (e.containsKey("width") && e.containsKey("height")) changed |= putIfChanged(p, ed, "res", e.getInt("width") + "x" + e.getInt("height"));
        if (e.containsKey("fps")) changed |= putIfChanged(p, ed, "fps", String.valueOf(e.getInt("fps")));
        if (e.containsKey("bitrate")) changed |= putIfChanged(p, ed, "bitrate", String.valueOf(Math.max(1, e.getInt("bitrate") / 1_000_000)));
        if (e.containsKey("audio")) {
            boolean a = e.getBoolean("audio");
            if (p.getBoolean("audio", true) != a) { ed.putBoolean("audio", a); changed = true; }
        }
        ed.apply();
        if (changed && CamService.instance != null) CamService.instance.reloadSettings();
    }

    @SuppressWarnings("deprecation")
    private void handleInstallStatus(Intent intent) {
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -999);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirm != null) startActivity(confirm);
        } else if (status != PackageInstaller.STATUS_SUCCESS) {
            String msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            Toast.makeText(this, "No se pudo actualizar: " + (msg != null ? msg : status), Toast.LENGTH_LONG).show();
        }
    }

    private static boolean putIfChanged(SharedPreferences p, SharedPreferences.Editor ed, String k, String v) {
        if (v == null || v.equals(p.getString(k, null))) return false;
        ed.putString(k, v);
        return true;
    }

    private SharedPreferences prefs() { return getSharedPreferences("cfg", MODE_PRIVATE); }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        hideSystemBars();
        if (hasPerms()) startCamService();
        else requestPerms();
        ui.post(refresh);
        Updater.check(this, false, (r, err) -> showUpdateChip(r));
    }

    @Override
    protected void onPause() {
        super.onPause();
        resumed = false;
        ui.removeCallbacks(refresh);
        detachPreview();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) hideSystemBars();
    }

    // =====================================================================
    // Permissions / service
    // =====================================================================

    private boolean hasPerms() {
        return checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestPerms() {
        List<String> req = new ArrayList<>();
        req.add(Manifest.permission.CAMERA);
        req.add(Manifest.permission.RECORD_AUDIO);
        if (Build.VERSION.SDK_INT >= 33) req.add(Manifest.permission.POST_NOTIFICATIONS);
        requestPermissions(req.toArray(new String[0]), 1);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (hasPerms()) startCamService();
        else tvEmpty.setText("Se necesita permiso de cámara.\nActívalo en Ajustes → Apps → PocketLens.");
    }

    private void startCamService() {
        Intent i = new Intent(this, CamService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i); else startService(i);
    }

    // =====================================================================
    // Preview
    // =====================================================================

    @Override public void onSurfaceTextureAvailable(SurfaceTexture st, int w, int h) { surfaceReady = true; }
    @Override public void onSurfaceTextureSizeChanged(SurfaceTexture st, int w, int h) { lastSize = null; }
    @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture st) { surfaceReady = false; detachPreview(); return true; }
    @Override public void onSurfaceTextureUpdated(SurfaceTexture st) { }

    private void attachPreviewIfNeeded() {
        CamService s = CamService.instance;
        if (s == null || !surfaceReady || !resumed || dimmed || previewAttached) return;
        previewAttached = true;
        s.setPreview(texture.getSurfaceTexture());
    }

    private void detachPreview() {
        if (!previewAttached) return;
        previewAttached = false;
        CamService s = CamService.instance;
        if (s != null) s.setPreview(null);
    }

    /** Fit the TextureView to the stream aspect ratio and rotate the buffer for the landscape display. */
    private void layoutPreview(Size size) {
        int bw = previewBox.getWidth(), bh = previewBox.getHeight();
        if (bw == 0 || bh == 0) return;
        float ar = (float) size.getWidth() / size.getHeight();
        int vw = bw, vh = Math.round(bw / ar);
        if (vh > bh) { vh = bh; vw = Math.round(bh * ar); }
        FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) texture.getLayoutParams();
        if (lp.width != vw || lp.height != vh) {
            lp.width = vw;
            lp.height = vh;
            lp.gravity = Gravity.CENTER;
            texture.setLayoutParams(lp);
        }
        int rotation = getWindowManager().getDefaultDisplay().getRotation();
        Matrix m = new Matrix();
        RectF view = new RectF(0, 0, vw, vh);
        RectF buf = new RectF(0, 0, size.getHeight(), size.getWidth());
        float cx = view.centerX(), cy = view.centerY();
        if (rotation == Surface.ROTATION_90 || rotation == Surface.ROTATION_270) {
            buf.offset(cx - buf.centerX(), cy - buf.centerY());
            m.setRectToRect(view, buf, Matrix.ScaleToFit.FILL);
            float scale = Math.max((float) vh / size.getHeight(), (float) vw / size.getWidth());
            m.postScale(scale, scale, cx, cy);
            m.postRotate(90 * (rotation - 2), cx, cy);
        } else if (rotation == Surface.ROTATION_180) {
            m.postRotate(180, cx, cy);
        }
        texture.setTransform(m);
    }

    // =====================================================================
    // UI helpers
    // =====================================================================

    private int dp(float v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    private GradientDrawable rounded(int color, float radiusDp, int stroke) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(radiusDp));
        if (stroke != 0) g.setStroke(dp(1), stroke);
        return g;
    }

    private GradientDrawable oval(int color) {
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(color);
        return g;
    }

    private Drawable ripple(Drawable content, boolean isOval) {
        GradientDrawable mask = new GradientDrawable();
        mask.setColor(Color.WHITE);
        if (isOval) mask.setShape(GradientDrawable.OVAL); else mask.setCornerRadius(dp(12));
        return new RippleDrawable(ColorStateList.valueOf(0x33FFFFFF), content, mask);
    }

    private Drawable icon(int res, int color) {
        Drawable d = getDrawable(res).mutate();
        d.setTint(color);
        return d;
    }

    private TextView text(String s, float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setTypeface(Typeface.create(bold ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        t.setIncludeFontPadding(false);
        return t;
    }

    private ImageView railButton(int res, String desc, View.OnClickListener l) {
        ImageView b = new ImageView(this);
        b.setImageDrawable(icon(res, TEXT));
        b.setContentDescription(desc);
        b.setScaleType(ImageView.ScaleType.CENTER);
        b.setBackground(ripple(oval(Color.TRANSPARENT), true));
        b.setOnClickListener(l);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(44), dp(44));
        lp.setMargins(dp(2), dp(1), dp(2), dp(1));
        b.setLayoutParams(lp);
        return b;
    }

    private void setRailState(ImageView b, int res, boolean active, int activeColor) {
        b.setImageDrawable(icon(res, active ? Color.BLACK : TEXT));
        b.setBackground(ripple(oval(active ? activeColor : Color.TRANSPARENT), true));
    }

    private View railDivider() {
        View v = new View(this);
        v.setBackgroundColor(STROKE);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(28), dp(1));
        lp.gravity = Gravity.CENTER;
        lp.setMargins(0, dp(4), 0, dp(4));
        v.setLayoutParams(lp);
        return v;
    }

    private LinearLayout infoRow(int iconRes, TextView value) {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setGravity(Gravity.CENTER_VERTICAL);
        r.setPadding(0, dp(5), 0, dp(5));
        ImageView i = new ImageView(this);
        i.setImageDrawable(icon(iconRes, TEXT_2));
        r.addView(i, new LinearLayout.LayoutParams(dp(18), dp(18)));
        value.setPadding(dp(10), 0, 0, 0);
        value.setSingleLine(true);
        value.setEllipsize(TextUtils.TruncateAt.END);
        r.addView(value);
        return r;
    }

    private TextView clientChip(int iconRes) {
        TextView t = text("0", 12, TEXT_2, true);
        Drawable d = icon(iconRes, TEXT_2);
        d.setBounds(0, 0, dp(14), dp(14));
        t.setCompoundDrawables(d, null, null, null);
        t.setCompoundDrawablePadding(dp(6));
        t.setGravity(Gravity.CENTER_VERTICAL);
        t.setPadding(dp(10), dp(6), dp(10), dp(6));
        t.setBackground(rounded(SURFACE_2, 14, 0));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(WRAP, WRAP);
        lp.setMargins(0, 0, dp(6), 0);
        t.setLayoutParams(lp);
        return t;
    }

    private void fade(View v, boolean show) {
        v.animate().cancel();
        if (show) {
            if (v.getVisibility() != View.VISIBLE) { v.setAlpha(0f); v.setVisibility(View.VISIBLE); }
            v.animate().alpha(1f).setDuration(160).start();
        } else if (v.getVisibility() == View.VISIBLE) {
            v.animate().alpha(0f).setDuration(220).withEndAction(() -> v.setVisibility(View.GONE)).start();
        }
    }

    private static String fmtZoom(float z) {
        return (z == Math.floor(z) ? String.valueOf((int) z) : String.format(Locale.US, "%.1f", z)) + "×";
    }

    // =====================================================================
    // Build UI
    // =====================================================================

    private void buildUi() {
        root = new FrameLayout(this);
        root.setBackgroundColor(BG);

        // ---- preview ----
        previewBox = new FrameLayout(this);
        texture = new TextureView(this);
        texture.setSurfaceTextureListener(this);
        previewBox.addView(texture, new FrameLayout.LayoutParams(1, 1, Gravity.CENTER));
        root.addView(previewBox, new FrameLayout.LayoutParams(MATCH, MATCH));
        setupGestures();

        // ---- empty state ----
        LinearLayout empty = new LinearLayout(this);
        empty.setOrientation(LinearLayout.VERTICAL);
        empty.setGravity(Gravity.CENTER);
        ImageView logoBig = new ImageView(this);
        logoBig.setImageDrawable(getDrawable(R.mipmap.ic_launcher));
        empty.addView(logoBig, new LinearLayout.LayoutParams(dp(72), dp(72)));
        tvEmpty = text("Iniciando cámara…", 15, TEXT_2, false);
        tvEmpty.setGravity(Gravity.CENTER);
        tvEmpty.setPadding(0, dp(16), 0, 0);
        empty.addView(tvEmpty);
        emptyState = empty;
        root.addView(empty, new FrameLayout.LayoutParams(MATCH, MATCH));

        // ---- HUD (hidden with double tap) ----
        FrameLayout hudBox = new FrameLayout(this);
        hud = hudBox;
        root.addView(hudBox, new FrameLayout.LayoutParams(MATCH, MATCH));

        View top = new View(this);
        top.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0xB3000000, 0x00000000}));
        hudBox.addView(top, new FrameLayout.LayoutParams(MATCH, dp(110), Gravity.TOP));
        View bot = new View(this);
        bot.setBackground(new GradientDrawable(GradientDrawable.Orientation.BOTTOM_TOP, new int[]{0xB3000000, 0x00000000}));
        hudBox.addView(bot, new FrameLayout.LayoutParams(MATCH, dp(150), Gravity.BOTTOM));

        hudBox.addView(buildTopBar(), new FrameLayout.LayoutParams(MATCH, WRAP, Gravity.TOP));

        FrameLayout.LayoutParams clp = new FrameLayout.LayoutParams(dp(300), WRAP, Gravity.BOTTOM | Gravity.START);
        clp.setMargins(dp(24), 0, 0, dp(20));
        hudBox.addView(buildConnectionCard(), clp);

        FrameLayout.LayoutParams rlp = new FrameLayout.LayoutParams(WRAP, WRAP, Gravity.END | Gravity.BOTTOM);
        rlp.setMargins(0, 0, dp(24), dp(20));
        hudBox.addView(buildRail(), rlp);

        FrameLayout.LayoutParams blp = new FrameLayout.LayoutParams(WRAP, WRAP, Gravity.BOTTOM | Gravity.END);
        blp.setMargins(0, 0, dp(100), dp(20));
        hudBox.addView(buildBottomControls(), blp);

        // big zoom indicator (pinch)
        tvZoomBig = text("1.0×", 28, TEXT, true);
        tvZoomBig.setPadding(dp(18), dp(8), dp(18), dp(8));
        tvZoomBig.setBackground(rounded(SURFACE, 22, 0));
        tvZoomBig.setVisibility(View.GONE);
        root.addView(tvZoomBig, new FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER));

        // ---- dim overlay ----
        FrameLayout dim = new FrameLayout(this);
        dim.setBackgroundColor(Color.BLACK);
        dim.setVisibility(View.GONE);
        dimText = text("", 13, 0xFF3A4048, false);
        dimText.setGravity(Gravity.CENTER);
        dim.addView(dimText, new FrameLayout.LayoutParams(MATCH, MATCH));
        dim.setOnClickListener(v -> setDimmed(false));
        dimOverlay = dim;
        root.addView(dim, new FrameLayout.LayoutParams(MATCH, MATCH));

        setContentView(root);
    }

    private View buildTopBar() {
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(24), dp(18), dp(24), 0);
        ImageView logo = new ImageView(this);
        logo.setImageDrawable(getDrawable(R.mipmap.ic_launcher));
        bar.addView(logo, new LinearLayout.LayoutParams(dp(34), dp(34)));
        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.setPadding(dp(12), 0, 0, 0);
        titles.addView(text("PocketLens", 16, TEXT, true));
        TextView sub = text(Build.MANUFACTURER.toUpperCase(Locale.ROOT) + " · " + Build.MODEL + " · v" + BuildInfo.VERSION, 11, TEXT_3, false);
        sub.setPadding(0, dp(4), 0, 0);
        titles.addView(sub);
        bar.addView(titles);
        bar.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1));

        tvUpdate = text("", 12, Color.BLACK, true);
        tvUpdate.setPadding(dp(12), dp(8), dp(12), dp(8));
        tvUpdate.setBackground(ripple(rounded(ACCENT, 16, 0), false));
        tvUpdate.setVisibility(View.GONE);
        tvUpdate.setOnClickListener(v -> { if (pendingUpdate != null) showUpdateDialog(pendingUpdate); });
        LinearLayout.LayoutParams ulp = new LinearLayout.LayoutParams(WRAP, WRAP);
        ulp.setMargins(0, 0, dp(10), 0);
        bar.addView(tvUpdate, ulp);

        tvStats = text("", 12, TEXT_2, true);
        tvStats.setPadding(dp(12), dp(8), dp(12), dp(8));
        tvStats.setBackground(rounded(SURFACE, 16, STROKE));
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(WRAP, WRAP);
        slp.setMargins(0, 0, dp(10), 0);
        bar.addView(tvStats, slp);

        statusPill = new LinearLayout(this);
        statusPill.setOrientation(LinearLayout.HORIZONTAL);
        statusPill.setGravity(Gravity.CENTER_VERTICAL);
        statusPill.setPadding(dp(12), dp(8), dp(14), dp(8));
        statusDot = new View(this);
        statusDot.setBackground(oval(TEXT_3));
        statusPill.addView(statusDot, new LinearLayout.LayoutParams(dp(8), dp(8)));
        tvStatus = text("EN ESPERA", 12, TEXT, true);
        tvStatus.setLetterSpacing(0.08f);
        tvStatus.setPadding(dp(8), 0, 0, 0);
        statusPill.addView(tvStatus);
        statusPill.setBackground(rounded(SURFACE, 16, STROKE));
        bar.addView(statusPill);
        return bar;
    }

    private View buildConnectionCard() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(14), dp(16), dp(14));
        card.setBackground(rounded(SURFACE, 16, STROKE));
        TextView hdr = text("CONECTAR DESDE EL PC", 10, TEXT_3, true);
        hdr.setLetterSpacing(0.12f);
        hdr.setPadding(0, 0, 0, dp(6));
        card.addView(hdr);
        card.addView(infoRow(R.drawable.ic_usb, text("USB · cliente PocketLens", 13, TEXT, false)));
        tvIp = text("Wi-Fi no conectado", 13, TEXT, false);
        tvIp.setTypeface(Typeface.MONOSPACE);
        card.addView(infoRow(R.drawable.ic_wifi, tvIp));
        tvWeb = text("", 13, TEXT, false);
        tvWeb.setTypeface(Typeface.MONOSPACE);
        card.addView(infoRow(R.drawable.ic_globe, tvWeb));
        LinearLayout chips = new LinearLayout(this);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        chips.setPadding(0, dp(10), 0, 0);
        tvPc = clientChip(R.drawable.ic_desktop);
        tvWebClients = clientChip(R.drawable.ic_globe);
        tvMic = clientChip(R.drawable.ic_mic);
        chips.addView(tvPc);
        chips.addView(tvWebClients);
        chips.addView(tvMic);
        card.addView(chips);
        return card;
    }

    private View buildRail() {
        LinearLayout rail = new LinearLayout(this);
        rail.setOrientation(LinearLayout.VERTICAL);
        rail.setGravity(Gravity.CENTER_HORIZONTAL);
        rail.setPadding(dp(4), dp(6), dp(4), dp(6));
        rail.setBackground(rounded(SURFACE, 32, STROKE));
        rail.addView(railButton(R.drawable.ic_switch, "Cambiar cámara", v -> {
            CamService s = CamService.instance;
            if (s != null) s.switchCamera();
        }));
        btTorch = railButton(R.drawable.ic_flash_off, "Linterna", v -> {
            CamService s = CamService.instance;
            if (s != null && s.hasFlash) s.setTorch(!s.torch);
        });
        rail.addView(btTorch);
        btMic = railButton(R.drawable.ic_mic, "Silenciar micrófono", v -> {
            CamService s = CamService.instance;
            if (s != null) s.setMicMuted(!s.micMuted);
        });
        rail.addView(btMic);
        rail.addView(railDivider());
        rail.addView(railButton(R.drawable.ic_moon, "Apagar pantalla", v -> setDimmed(true)));
        rail.addView(railButton(R.drawable.ic_tune, "Ajustes", v -> showSettings()));
        rail.addView(railDivider());
        ImageView power = railButton(R.drawable.ic_power, "Detener", v -> {
            detachPreview();
            stopService(new Intent(this, CamService.class));
            finishAndRemoveTask();
        });
        power.setImageDrawable(icon(R.drawable.ic_power, LIVE));
        rail.addView(power);
        return rail;
    }

    private View buildBottomControls() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.END);

        expBar = new LinearLayout(this);
        expBar.setOrientation(LinearLayout.HORIZONTAL);
        expBar.setGravity(Gravity.CENTER_VERTICAL);
        expBar.setPadding(dp(14), dp(4), dp(14), dp(4));
        expBar.setBackground(rounded(SURFACE, 22, STROKE));
        ImageView sun = new ImageView(this);
        sun.setImageDrawable(icon(R.drawable.ic_exposure, WARN));
        expBar.addView(sun, new LinearLayout.LayoutParams(dp(18), dp(18)));
        sbExp = new SeekBar(this);
        sbExp.setProgressTintList(ColorStateList.valueOf(WARN));
        sbExp.setThumbTintList(ColorStateList.valueOf(WARN));
        sbExp.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar sb, int p, boolean fromUser) {
                CamService s = CamService.instance;
                if (fromUser && s != null) {
                    s.setExposure(s.expMin + p);
                    ui.removeCallbacks(hideExp);
                    ui.postDelayed(hideExp, 4000);
                }
            }
            @Override public void onStartTrackingTouch(SeekBar sb) { userTouchingExp = true; }
            @Override public void onStopTrackingTouch(SeekBar sb) { userTouchingExp = false; }
        });
        expBar.addView(sbExp, new LinearLayout.LayoutParams(dp(180), dp(36)));
        tvExp = text("0", 12, TEXT, true);
        tvExp.setMinWidth(dp(28));
        tvExp.setGravity(Gravity.END);
        expBar.addView(tvExp);
        expBar.setVisibility(View.GONE);
        LinearLayout.LayoutParams elp = new LinearLayout.LayoutParams(WRAP, WRAP);
        elp.setMargins(0, 0, 0, dp(10));
        col.addView(expBar, elp);

        LinearLayout zoomBar = new LinearLayout(this);
        zoomBar.setOrientation(LinearLayout.HORIZONTAL);
        zoomBar.setGravity(Gravity.CENTER);
        zoomBar.setPadding(dp(4), dp(4), dp(4), dp(4));
        zoomBar.setBackground(rounded(SURFACE, 24, STROKE));
        for (float z : new float[]{1f, 2f, 5f}) {
            TextView t = text(fmtZoom(z), 12, TEXT, true);
            t.setGravity(Gravity.CENTER);
            t.setTag(z);
            t.setOnClickListener(v -> {
                CamService s = CamService.instance;
                if (s != null) s.setZoom((Float) v.getTag());
            });
            LinearLayout.LayoutParams zl = new LinearLayout.LayoutParams(dp(40), dp(40));
            zl.setMargins(dp(2), 0, dp(2), 0);
            zoomBar.addView(t, zl);
            zoomPresets.add(t);
        }
        col.addView(zoomBar, new LinearLayout.LayoutParams(WRAP, WRAP));
        return col;
    }

    private void setupGestures() {
        scaleDetector = new ScaleGestureDetector(this, new ScaleGestureDetector.SimpleOnScaleGestureListener() {
            @Override public boolean onScale(ScaleGestureDetector d) {
                CamService s = CamService.instance;
                if (s == null) return false;
                s.setZoom(s.zoom * d.getScaleFactor());
                tvZoomBig.setText(String.format(Locale.US, "%.1f×", s.zoom));
                fade(tvZoomBig, true);
                ui.removeCallbacks(hideZoomBig);
                ui.postDelayed(hideZoomBig, 900);
                return true;
            }
        });
        gestureDetector = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override public boolean onSingleTapConfirmed(MotionEvent e) {
                CamService s = CamService.instance;
                if (s == null) return false;
                float nx = e.getX() / texture.getWidth(), ny = e.getY() / texture.getHeight();
                if ("front".equals(s.facing)) nx = 1 - nx; // front preview is mirrored
                s.focusAt(nx, ny);
                showFocusRing(e.getX() + texture.getLeft(), e.getY() + texture.getTop());
                if (s.expMax > s.expMin && !hudHidden) {
                    fade(expBar, true);
                    ui.removeCallbacks(hideExp);
                    ui.postDelayed(hideExp, 4000);
                }
                return true;
            }

            @Override public boolean onDoubleTap(MotionEvent e) {
                hudHidden = !hudHidden;
                fade(hud, !hudHidden);
                return true;
            }
        });
        texture.setOnTouchListener((v, ev) -> {
            scaleDetector.onTouchEvent(ev);
            if (!scaleDetector.isInProgress()) gestureDetector.onTouchEvent(ev);
            return true;
        });
    }

    private void showFocusRing(float x, float y) {
        View ring = new View(this);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setStroke(dp(2), WARN);
        ring.setBackground(g);
        int sz = dp(72);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(sz, sz);
        lp.leftMargin = (int) x - sz / 2;
        lp.topMargin = (int) y - sz / 2;
        ring.setScaleX(1.3f);
        ring.setScaleY(1.3f);
        previewBox.addView(ring, lp);
        ring.animate().scaleX(1f).scaleY(1f).setDuration(180).withEndAction(() ->
                ring.animate().alpha(0f).setStartDelay(700).setDuration(400)
                        .withEndAction(() -> previewBox.removeView(ring)).start()).start();
    }

    private void setDimmed(boolean on) {
        dimmed = on;
        if (on) {
            dimOverlay.setAlpha(0f);
            dimOverlay.setVisibility(View.VISIBLE);
            dimOverlay.animate().alpha(1f).setDuration(250).start();
        } else {
            dimOverlay.setVisibility(View.GONE);
        }
        WindowManager.LayoutParams lp = getWindow().getAttributes();
        lp.screenBrightness = on ? 0.01f : WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE;
        getWindow().setAttributes(lp);
        if (on) detachPreview();
    }

    private void hideSystemBars() {
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                c.hide(WindowInsets.Type.systemBars());
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        }
    }

    // =====================================================================
    // Settings sheet
    // =====================================================================

    /** Segmented control; value() returns the selected option. */
    private final class Segmented {
        final LinearLayout view;
        final String[] values;
        final List<TextView> items = new ArrayList<>();
        int selected = 0;

        Segmented(String[] labels, String[] values, String current) {
            this.values = values;
            view = new LinearLayout(MainActivity.this);
            view.setOrientation(LinearLayout.HORIZONTAL);
            view.setPadding(dp(3), dp(3), dp(3), dp(3));
            view.setBackground(rounded(SURFACE_2, 10, 0));
            for (int i = 0; i < values.length; i++) if (values[i].equals(current)) selected = i;
            for (int i = 0; i < labels.length; i++) {
                final int idx = i;
                TextView t = text(labels[i], 13, TEXT_2, true);
                t.setGravity(Gravity.CENTER);
                t.setPadding(dp(8), dp(7), dp(8), dp(7));
                t.setOnClickListener(v -> { selected = idx; paint(); });
                view.addView(t, new LinearLayout.LayoutParams(0, WRAP, 1));
                items.add(t);
            }
            paint();
        }

        void paint() {
            for (int i = 0; i < items.size(); i++) {
                boolean on = i == selected;
                items.get(i).setTextColor(on ? Color.BLACK : TEXT_2);
                items.get(i).setBackground(on ? rounded(ACCENT, 8, 0) : null);
            }
        }

        String value() { return values[selected]; }
    }

    private TextView sectionTitle(String s) {
        TextView t = text(s, 10, TEXT_3, true);
        t.setLetterSpacing(0.12f);
        t.setPadding(0, dp(12), 0, dp(6));
        return t;
    }

    private View labeled(String label, View control) {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setGravity(Gravity.CENTER_VERTICAL);
        r.setPadding(0, dp(3), 0, dp(3));
        r.addView(text(label, 14, TEXT, false), new LinearLayout.LayoutParams(dp(110), WRAP));
        r.addView(control, new LinearLayout.LayoutParams(0, WRAP, 1));
        return r;
    }

    private void showSettings() {
        SharedPreferences p = prefs();
        Dialog d = new Dialog(this, android.R.style.Theme_Material_Dialog_NoActionBar);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24), dp(16), dp(24), dp(14));
        box.setBackground(rounded(0xFF12161C, 20, STROKE));

        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);
        ImageView hi = new ImageView(this);
        hi.setImageDrawable(icon(R.drawable.ic_tune, ACCENT));
        head.addView(hi, new LinearLayout.LayoutParams(dp(22), dp(22)));
        TextView title = text("Ajustes", 20, TEXT, true);
        title.setPadding(dp(12), 0, 0, 0);
        head.addView(title);
        box.addView(head);

        box.addView(sectionTitle("VÍDEO"));
        Segmented res = new Segmented(new String[]{"480p", "720p", "1080p"},
                new String[]{"640x480", "1280x720", "1920x1080"}, p.getString("res", "1280x720"));
        box.addView(labeled("Resolución", res.view));
        Segmented fps = new Segmented(new String[]{"15", "24", "30", "60"},
                new String[]{"15", "24", "30", "60"}, p.getString("fps", "30"));
        box.addView(labeled("FPS", fps.view));
        Segmented br = new Segmented(new String[]{"Baja", "Media", "Alta", "Máx."},
                new String[]{"2", "6", "10", "16"}, p.getString("bitrate", "6"));
        box.addView(labeled("Calidad", br.view));

        box.addView(sectionTitle("AUDIO"));
        Switch audio = new Switch(this);
        audio.setText("Enviar micrófono al PC");
        audio.setTextColor(TEXT);
        audio.setTextSize(14);
        audio.setChecked(p.getBoolean("audio", true));
        int[][] states = {{android.R.attr.state_checked}, {}};
        audio.setThumbTintList(new ColorStateList(states, new int[]{ACCENT, 0xFF9AA1AA}));
        audio.setTrackTintList(new ColorStateList(states, new int[]{ACCENT_DARK, 0xFF3A414B}));
        box.addView(audio);

        box.addView(sectionTitle("ACERCA DE"));
        TextView about = text("v" + BuildInfo.VERSION + " · Puertos " + CamService.PORT_VIDEO + "/" + CamService.PORT_AUDIO + "/" + CamService.PORT_HTTP
                + " · Tocar: enfocar · Pellizcar: zoom · Doble toque: ocultar controles", 12, TEXT_2, false);
        about.setLineSpacing(dp(4), 1f);
        box.addView(about);
        TextView checkUpd = text("Buscar actualizaciones", 13, ACCENT, true);
        checkUpd.setPadding(0, dp(10), 0, dp(4));
        checkUpd.setOnClickListener(v -> {
            checkUpd.setText("Buscando…");
            Updater.check(this, true, (r, err) -> {
                checkUpd.setText("Buscar actualizaciones");
                if (err != null) Toast.makeText(this, "Sin conexión con GitHub: " + err, Toast.LENGTH_LONG).show();
                else if (r == null) Toast.makeText(this, "Tienes la última versión (v" + BuildInfo.VERSION + ")", Toast.LENGTH_SHORT).show();
                else { d.dismiss(); showUpdateChip(r); showUpdateDialog(r); }
            });
        });
        box.addView(checkUpd);

        LinearLayout buttons = new LinearLayout(this);
        buttons.setGravity(Gravity.END);
        buttons.setPadding(0, dp(12), 0, 0);
        TextView cancel = text("Cancelar", 14, TEXT_2, true);
        cancel.setPadding(dp(18), dp(11), dp(18), dp(11));
        cancel.setBackground(ripple(new ColorDrawable(Color.TRANSPARENT), false));
        cancel.setOnClickListener(v -> d.dismiss());
        TextView apply = text("Aplicar", 14, Color.BLACK, true);
        apply.setPadding(dp(24), dp(11), dp(24), dp(11));
        apply.setBackground(ripple(rounded(ACCENT, 12, 0), false));
        apply.setOnClickListener(v -> {
            p.edit().putString("res", res.value()).putString("fps", fps.value()).putString("bitrate", br.value())
                    .putBoolean("audio", audio.isChecked()).apply();
            if (audio.isChecked() && checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 2);
            }
            if (CamService.instance != null) CamService.instance.reloadSettings();
            d.dismiss();
        });
        buttons.addView(cancel);
        LinearLayout.LayoutParams alp = new LinearLayout.LayoutParams(WRAP, WRAP);
        alp.setMargins(dp(8), 0, 0, 0);
        buttons.addView(apply, alp);
        box.addView(buttons);

        ScrollView sv = new ScrollView(this);
        sv.addView(box);
        d.setContentView(sv);
        Window w = d.getWindow();
        if (w != null) {
            w.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            w.setLayout(dp(560), WRAP);
            w.setDimAmount(0.6f);
        }
        d.setOnDismissListener(x -> hideSystemBars());
        d.show();
    }

    // =====================================================================
    // Updates
    // =====================================================================

    private void showUpdateChip(Updater.Release r) {
        pendingUpdate = r;
        if (r == null) { tvUpdate.setVisibility(View.GONE); return; }
        tvUpdate.setText("Actualizar a v" + r.version);
        tvUpdate.setVisibility(View.VISIBLE);
    }

    private void showUpdateDialog(Updater.Release r) {
        Dialog d = new Dialog(this, android.R.style.Theme_Material_Dialog_NoActionBar);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24), dp(18), dp(24), dp(16));
        box.setBackground(rounded(0xFF12161C, 20, STROKE));
        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);
        ImageView logo = new ImageView(this);
        logo.setImageDrawable(getDrawable(R.mipmap.ic_launcher));
        head.addView(logo, new LinearLayout.LayoutParams(dp(36), dp(36)));
        LinearLayout tcol = new LinearLayout(this);
        tcol.setOrientation(LinearLayout.VERTICAL);
        tcol.setPadding(dp(12), 0, 0, 0);
        tcol.addView(text("Nueva versión disponible", 18, TEXT, true));
        TextView vv = text("v" + BuildInfo.VERSION + "  →  v" + r.version
                + (r.size > 0 ? String.format(Locale.US, "  ·  %.1f MB", r.size / 1048576f) : ""), 12, TEXT_2, false);
        vv.setPadding(0, dp(4), 0, 0);
        tcol.addView(vv);
        head.addView(tcol);
        box.addView(head);
        TextView notes = text(r.notes == null || r.notes.trim().isEmpty() ? "Mejoras y correcciones." : r.notes.trim(), 13, TEXT_2, false);
        notes.setLineSpacing(dp(3), 1f);
        ScrollView ns = new ScrollView(this);
        ns.setPadding(0, dp(14), 0, dp(6));
        ns.addView(notes);
        box.addView(ns, new LinearLayout.LayoutParams(MATCH, dp(130)));
        ProgressBar bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setProgressTintList(ColorStateList.valueOf(ACCENT));
        bar.setVisibility(View.GONE);
        box.addView(bar, new LinearLayout.LayoutParams(MATCH, dp(10)));
        LinearLayout buttons = new LinearLayout(this);
        buttons.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        buttons.setPadding(0, dp(12), 0, 0);
        TextView later = text("Más tarde", 14, TEXT_2, true);
        later.setPadding(dp(18), dp(11), dp(18), dp(11));
        later.setBackground(ripple(new ColorDrawable(Color.TRANSPARENT), false));
        later.setOnClickListener(v -> d.dismiss());
        TextView go = text("Actualizar", 14, Color.BLACK, true);
        go.setPadding(dp(24), dp(11), dp(24), dp(11));
        go.setBackground(ripple(rounded(ACCENT, 12, 0), false));
        go.setOnClickListener(v -> {
            if (Updater.needsInstallPermission(this)) {
                Toast.makeText(this, "Permite «Instalar apps desconocidas» para PocketLens y vuelve a pulsar Actualizar.",
                        Toast.LENGTH_LONG).show();
                return;
            }
            go.setEnabled(false);
            later.setEnabled(false);
            go.setText("Descargando…");
            bar.setVisibility(View.VISIBLE);
            Updater.downloadAndInstall(this, r, new Updater.ProgressCallback() {
                @Override public void progress(int pct) {
                    bar.setProgress(pct);
                    go.setText("Descargando " + pct + "%");
                }
                @Override public void done(String error) {
                    if (error != null) {
                        go.setEnabled(true);
                        later.setEnabled(true);
                        go.setText("Reintentar");
                        Toast.makeText(MainActivity.this, "Error al descargar: " + error, Toast.LENGTH_LONG).show();
                    } else {
                        go.setText("Instalando…");
                        d.dismiss();
                    }
                }
            });
        });
        buttons.addView(later);
        LinearLayout.LayoutParams glp = new LinearLayout.LayoutParams(WRAP, WRAP);
        glp.setMargins(dp(8), 0, 0, 0);
        buttons.addView(go, glp);
        box.addView(buttons);
        d.setContentView(box);
        Window w = d.getWindow();
        if (w != null) {
            w.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            w.setLayout(dp(520), WRAP);
            w.setDimAmount(0.6f);
        }
        d.setOnDismissListener(x -> hideSystemBars());
        d.show();
    }

    // =====================================================================
    // Periodic refresh
    // =====================================================================

    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            update();
            ui.postDelayed(this, 300);
        }
    };

    private void update() {
        CamService s = CamService.instance;
        attachPreviewIfNeeded();
        String ip = wifiIp();
        tvIp.setText(ip != null ? ip : "Wi-Fi no conectado");
        tvWeb.setText(ip != null ? "http://" + ip + ":" + CamService.PORT_HTTP : "—");
        if (s == null) {
            emptyState.setVisibility(View.VISIBLE);
            return;
        }
        Size size = s.curSize;
        if (size != null && !size.equals(lastSize) && previewBox.getWidth() > 0) {
            layoutPreview(size);
            lastSize = size;
        }
        emptyState.setVisibility(s.cameraActive || dimmed ? View.GONE : View.VISIBLE);
        if (!s.cameraActive) tvEmpty.setText(CamService.status.startsWith("Error") ? CamService.status : "Iniciando cámara…");

        boolean live = s.clientCount() > 0 || s.webCount() > 0;
        tvStatus.setText(live ? "EN VIVO" : "EN ESPERA");
        ((GradientDrawable) statusDot.getBackground()).setColor(live ? LIVE : TEXT_3);
        statusPill.setBackground(rounded(live ? 0x40EF4444 : SURFACE, 16, live ? 0x80EF4444 : STROKE));

        if (size != null && s.cameraActive) {
            tvStats.setVisibility(View.VISIBLE);
            tvStats.setText(String.format(Locale.US, "%s   ·   %d×%d   ·   %d fps   ·   %.1f Mbps",
                    "front".equals(s.facing) ? "Frontal" : "Trasera", size.getWidth(), size.getHeight(),
                    s.statFps, s.statKbps / 1000f));
        } else {
            tvStats.setVisibility(View.GONE);
        }
        tvPc.setText("PC " + s.clientCount());
        tvWebClients.setText("Web " + s.webCount());
        tvMic.setText(!s.audioEnabled ? "Mic off" : (s.micMuted ? "Silenciado" : "Mic " + s.audioClients.get()));
        tintChip(tvPc, s.clientCount() > 0, ACCENT);
        tintChip(tvWebClients, s.webCount() > 0, ACCENT);
        tintChip(tvMic, s.micMuted || s.audioClients.get() > 0, s.micMuted ? LIVE : ACCENT);

        setRailState(btTorch, s.torch ? R.drawable.ic_flash : R.drawable.ic_flash_off, s.torch, WARN);
        btTorch.setAlpha(s.hasFlash ? 1f : 0.35f);
        setRailState(btMic, s.micMuted ? R.drawable.ic_mic_off : R.drawable.ic_mic, s.micMuted, LIVE);

        for (TextView t : zoomPresets) {
            float z = (Float) t.getTag();
            t.setVisibility(z <= s.maxZoom + 0.01f ? View.VISIBLE : View.GONE);
            boolean on = Math.abs(s.zoom - z) < 0.05f;
            t.setTextColor(on ? Color.BLACK : TEXT);
            t.setBackground(ripple(oval(on ? TEXT : Color.TRANSPARENT), true));
        }

        int range = s.expMax - s.expMin;
        if (range > 0) {
            if (sbExp.getMax() != range) sbExp.setMax(range);
            if (!userTouchingExp) sbExp.setProgress(s.exposure - s.expMin);
            tvExp.setText((s.exposure > 0 ? "+" : "") + s.exposure);
        }
        if (dimmed) dimText.setText((live ? "● EN VIVO" : "En espera") + "\n\nToca para encender la pantalla");
    }

    private void tintChip(TextView t, boolean active, int color) {
        int c = active ? color : TEXT_2;
        t.setTextColor(c);
        Drawable d = t.getCompoundDrawables()[0];
        if (d != null) d.setTint(c);
        t.setBackground(rounded(active ? (color & 0x00FFFFFF) | 0x26000000 : SURFACE_2, 14, 0));
    }

    private String wifiIp() {
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                String n = ni.getName();
                if (!n.startsWith("wlan") && !n.startsWith("ap") && !n.startsWith("swlan") && !n.startsWith("eth")) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address) return a.getHostAddress();
                }
            }
        } catch (Exception ignored) { }
        return null;
    }
}
