package com.webcam.adb;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Self-update from GitHub Releases (latest release, first *.apk asset). */
final class Updater {
    static final String ACTION_INSTALL_STATUS = "com.webcam.adb.INSTALL_STATUS";
    private static final long CHECK_INTERVAL_MS = 6 * 3600 * 1000L;
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    static final class Release {
        String version, apkUrl, notes, page;
        long size;
    }

    interface CheckCallback { void done(Release newer, String error); }

    interface ProgressCallback {
        void progress(int percent);
        void done(String error);
    }

    private Updater() { }

    static int[] parse(String v) {
        String[] p = v.replaceFirst("^[vV]", "").split("[.\\-+]");
        int[] r = new int[3];
        for (int i = 0; i < 3 && i < p.length; i++) {
            try { r[i] = Integer.parseInt(p[i]); } catch (NumberFormatException ignored) { }
        }
        return r;
    }

    static boolean isNewer(String candidate, String current) {
        int[] a = parse(candidate), b = parse(current);
        for (int i = 0; i < 3; i++) if (a[i] != b[i]) return a[i] > b[i];
        return false;
    }

    private static SharedPreferences prefs(Context c) { return c.getSharedPreferences("update", Context.MODE_PRIVATE); }

    static Release fetchLatest() throws Exception {
        if (BuildInfo.REPO.isEmpty()) throw new IllegalStateException("sin repositorio configurado");
        HttpURLConnection c = (HttpURLConnection) new URL(
                "https://api.github.com/repos/" + BuildInfo.REPO + "/releases/latest").openConnection();
        c.setRequestProperty("Accept", "application/vnd.github+json");
        c.setRequestProperty("User-Agent", "PocketLens-Android/" + BuildInfo.VERSION);
        c.setConnectTimeout(8000);
        c.setReadTimeout(8000);
        int code = c.getResponseCode();
        if (code != 200) throw new IllegalStateException("GitHub respondió " + code);
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        try (InputStream in = c.getInputStream()) {
            byte[] b = new byte[16384];
            int n;
            while ((n = in.read(b)) > 0) bos.write(b, 0, n);
        }
        JSONObject j = new JSONObject(new String(bos.toByteArray(), StandardCharsets.UTF_8));
        Release r = new Release();
        r.version = j.getString("tag_name").replaceFirst("^[vV]", "");
        r.notes = j.optString("body", "");
        r.page = j.optString("html_url", "");
        JSONArray assets = j.optJSONArray("assets");
        if (assets != null) {
            for (int i = 0; i < assets.length(); i++) {
                JSONObject a = assets.getJSONObject(i);
                if (a.getString("name").endsWith(".apk")) {
                    r.apkUrl = a.getString("browser_download_url");
                    r.size = a.optLong("size");
                    break;
                }
            }
        }
        return r;
    }

    /** Checks at most every 6 h unless force. Callback runs on the main thread. */
    static void check(Context ctx, boolean force, CheckCallback cb) {
        SharedPreferences p = prefs(ctx);
        long now = System.currentTimeMillis();
        if (!force && now - p.getLong("last", 0) < CHECK_INTERVAL_MS) {
            String v = p.getString("version", null);
            if (v != null && isNewer(v, BuildInfo.VERSION) && p.getString("url", null) != null) {
                Release r = new Release();
                r.version = v;
                r.apkUrl = p.getString("url", null);
                r.notes = p.getString("notes", "");
                r.size = p.getLong("size", 0);
                cb.done(r, null);
            } else {
                cb.done(null, null);
            }
            return;
        }
        new Thread(() -> {
            try {
                Release r = fetchLatest();
                p.edit().putLong("last", now).putString("version", r.version).putString("url", r.apkUrl)
                        .putString("notes", r.notes).putLong("size", r.size).apply();
                boolean newer = r.apkUrl != null && isNewer(r.version, BuildInfo.VERSION);
                MAIN.post(() -> cb.done(newer ? r : null, null));
            } catch (Exception e) {
                MAIN.post(() -> cb.done(null, e.getMessage()));
            }
        }, "update-check").start();
    }

    /** True if the user still has to allow "install unknown apps" for us (settings screen is opened). */
    static boolean needsInstallPermission(Activity a) {
        if (Build.VERSION.SDK_INT >= 26 && !a.getPackageManager().canRequestPackageInstalls()) {
            a.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + a.getPackageName())));
            return true;
        }
        return false;
    }

    static void downloadAndInstall(Activity a, Release r, ProgressCallback cb) {
        new Thread(() -> {
            File f = new File(a.getCacheDir(), "update.apk");
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(r.apkUrl).openConnection();
                c.setInstanceFollowRedirects(true);
                c.setRequestProperty("User-Agent", "PocketLens-Android/" + BuildInfo.VERSION);
                c.setConnectTimeout(10000);
                c.setReadTimeout(20000);
                long total = c.getContentLengthLong() > 0 ? c.getContentLengthLong() : r.size;
                try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(f)) {
                    byte[] b = new byte[65536];
                    long got = 0;
                    int n, last = -1;
                    while ((n = in.read(b)) > 0) {
                        out.write(b, 0, n);
                        got += n;
                        int pct = total > 0 ? (int) (got * 100 / total) : 0;
                        if (pct != last) {
                            last = pct;
                            final int fp = pct;
                            MAIN.post(() -> cb.progress(fp));
                        }
                    }
                }
                install(a, f);
                MAIN.post(() -> cb.done(null));
            } catch (Exception e) {
                MAIN.post(() -> cb.done(e.getMessage() != null ? e.getMessage() : e.toString()));
            }
        }, "update-download").start();
    }

    private static void install(Activity a, File apk) throws Exception {
        PackageInstaller pi = a.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(a.getPackageName());
        int id = pi.createSession(params);
        try (PackageInstaller.Session s = pi.openSession(id)) {
            try (InputStream in = new FileInputStream(apk); OutputStream out = s.openWrite("base.apk", 0, apk.length())) {
                byte[] b = new byte[65536];
                int n;
                while ((n = in.read(b)) > 0) out.write(b, 0, n);
                s.fsync(out);
            }
            Intent i = new Intent(a, MainActivity.class).setAction(ACTION_INSTALL_STATUS);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
            PendingIntent p = PendingIntent.getActivity(a, 7, i, flags);
            s.commit(p.getIntentSender());
        }
    }
}
