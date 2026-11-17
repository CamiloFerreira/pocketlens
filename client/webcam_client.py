#!/usr/bin/env python3
"""
PocketLens — desktop client (Linux & Windows).

Turns the phone running the PocketLens app into a virtual webcam + microphone.
  Linux   : v4l2loopback camera + PipeWire "Android Mic"
  Windows : OBS Virtual Camera + any audio output (VB-Cable)
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

import engine as E

# =============================================================================
# Design tokens
# =============================================================================

C = {
    "bg": "#0b0d10", "panel": "#111419", "card": "#161a20", "card2": "#1c2129", "line": "#242a33",
    "text": "#eef1f4", "text2": "#a3abb5", "text3": "#6b737d",
    "accent": "#22c55e", "accent2": "#16a34a", "live": "#ef4444", "warn": "#f59e0b", "info": "#38bdf8",
}

ICONS = {
    "switch": "M9,12c0,1.66 1.34,3 3,3s3,-1.34 3,-3s-1.34,-3 -3,-3S9,10.34 9,12z M8,10V8H5.09C6.47,5.61 9.05,4 12,4c3.72,0 6.85,2.56 7.74,6h2.06c-0.93,-4.56 -4.96,-8 -9.8,-8C8.73,2 5.82,3.58 4,6.01V4H2v6H8z M16,14v2h2.91c-1.38,2.39 -3.96,4 -6.91,4c-3.72,0 -6.85,-2.56 -7.74,-6H2.2c0.93,4.56 4.96,8 9.8,8c3.27,0 6.18,-1.58 8,-4.01V20h2v-6H16z",
    "flash": "M7,2v11h3v9l7,-12h-4l4,-8z",
    "mic": "M12,14c1.66,0 2.99,-1.34 2.99,-3L15,5c0,-1.66 -1.34,-3 -3,-3S9,3.34 9,5v6c0,1.66 1.34,3 3,3zM17.3,11c0,3 -2.54,5.1 -5.3,5.1S6.7,14 6.7,11H5c0,3.41 2.72,6.23 6,6.72V21h2v-3.28c3.28,-0.48 6,-3.3 6,-6.72h-1.7z",
    "mic_off": "M19,11h-1.7c0,0.74 -0.16,1.43 -0.43,2.05l1.23,1.23c0.56,-0.98 0.9,-2.09 0.9,-3.28zM14.98,11.17c0,-0.06 0.02,-0.11 0.02,-0.17V5c0,-1.66 -1.34,-3 -3,-3S9,3.34 9,5v0.18l5.98,5.99zM4.27,3L3,4.27l6.01,6.01V11c0,1.66 1.33,3 2.99,3 0.22,0 0.44,-0.03 0.65,-0.08l1.66,1.66c-0.71,0.33 -1.5,0.52 -2.31,0.52 -2.76,0 -5.3,-2.1 -5.3,-5.1H5c0,3.41 2.72,6.23 6,6.72V21h2v-3.28c0.91,-0.13 1.77,-0.45 2.54,-0.9L19.73,21 21,19.73 4.27,3z",
    "videocam": "M17,10.5V7c0,-0.55 -0.45,-1 -1,-1H4c-0.55,0 -1,0.45 -1,1v10c0,0.55 0.45,1 1,1h12c0.55,0 1,-0.45 1,-1v-3.5l4,4v-11l-4,4z",
    "wifi": "M1,9l2,2c4.97,-4.97 13.03,-4.97 18,0l2,-2C16.93,2.93 7.08,2.93 1,9zM9,17l3,3 3,-3c-1.65,-1.66 -4.34,-1.66 -6,0zM5,13l2,2c2.76,-2.76 7.24,-2.76 10,0l2,-2C15.14,9.14 8.87,9.14 5,13z",
    "usb": "M15,7v4h1v2h-3V5h2l-3,-4 -3,4h2v8H8v-2.07c0.7,-0.37 1.2,-1.08 1.2,-1.93 0,-1.21 -0.99,-2.2 -2.2,-2.2 -1.21,0 -2.2,0.99 -2.2,2.2 0,0.85 0.5,1.56 1.2,1.93V13c0,1.11 0.89,2 2,2h3v3.05c-0.71,0.37 -1.2,1.1 -1.2,1.95 0,1.22 0.99,2.2 2.2,2.2 1.21,0 2.2,-0.98 2.2,-2.2 0,-0.85 -0.49,-1.58 -1.2,-1.95V15h3c1.11,0 2,-0.89 2,-2v-2h1V7h-4z",
    "phone": "M16,1H8C6.34,1 5,2.34 5,4v16c0,1.66 1.34,3 3,3h8c1.66,0 3,-1.34 3,-3V4c0,-1.66 -1.34,-3 -3,-3zM14,21h-4v-1h4v1zM17.25,18H6.75V4h10.5v14z",
    "camera": "M12,15.2c1.77,0 3.2,-1.43 3.2,-3.2S13.77,8.8 12,8.8 8.8,10.23 8.8,12s1.43,3.2 3.2,3.2zM9,2L7.17,4H4c-1.1,0 -2,0.9 -2,2v12c0,1.1 0.9,2 2,2h16c1.1,0 2,-0.9 2,-2V6c0,-1.1 -0.9,-2 -2,-2h-3.17L15,2H9zM12,17c-2.76,0 -5,-2.24 -5,-5s2.24,-5 5,-5 5,2.24 5,5 -2.24,5 -5,5z",
    "flip": "M15,21h2v-2h-2v2zM19,9h2V7h-2v2zM3,5v14c0,1.1 0.9,2 2,2h4v-2H5V5h4V3H5c-1.1,0 -2,0.9 -2,2zM19,3v2h2c0,-1.1 -0.9,-2 -2,-2zM11,23h2V1h-2v22zM19,17h2v-2h-2v2zM15,5h2V3h-2v2zM19,13h2v-2h-2v2zM19,21c1.1,0 2,-0.9 2,-2h-2v2z",
    "fullscreen": "M7,14H5v5h5v-2H7v-3zM5,10h2V7h3V5H5v5zM17,17h-3v2h5v-5h-2v3zM14,5v2h3v3h2V5h-5z",
    "zoom": "M15.5,14h-0.79l-0.28,-0.27C15.41,12.59 16,11.11 16,9.5 16,5.91 13.09,3 9.5,3S3,5.91 3,9.5 5.91,16 9.5,16c1.61,0 3.09,-0.59 4.23,-1.57l0.27,0.28v0.79l5,4.99L20.49,19l-4.99,-5zM9.5,14C7.01,14 5,11.99 5,9.5S7.01,5 9.5,5 14,7.01 14,9.5 11.99,14 9.5,14zM12,10h-2v2H9v-2H7V9h2V7h1v2h2v1z",
    "exposure": "M20,8.69V4h-4.69L12,0.69 8.69,4H4v4.69L0.69,12 4,15.31V20h4.69L12,23.31 15.31,20H20v-4.69L23.31,12 20,8.69zM12,18c-3.31,0 -6,-2.69 -6,-6s2.69,-6 6,-6 6,2.69 6,6 -2.69,6 -6,6zM12,8c-2.21,0 -4,1.79 -4,4s1.79,4 4,4 4,-1.79 4,-4 -1.79,-4 -4,-4z",
    "refresh": "M17.65,6.35C16.2,4.9 14.21,4 12,4c-4.42,0 -7.99,3.58 -7.99,8s3.57,8 7.99,8c3.73,0 6.84,-2.55 7.73,-6h-2.08c-0.82,2.33 -3.04,4 -5.65,4 -3.31,0 -6,-2.69 -6,-6s2.69,-6 6,-6c1.66,0 3.14,0.69 4.22,1.78L13,11h7V4l-2.35,2.35z",
    "speaker": "M3,9v6h4l5,5V4L7,9H3zM16.5,12c0,-1.77 -1.02,-3.29 -2.5,-4.03v8.05c1.48,-0.73 2.5,-2.25 2.5,-4.02zM14,3.23v2.06c2.89,0.86 5,3.54 5,6.71s-2.11,5.85 -5,6.71v2.06c4.01,-0.91 7,-4.49 7,-8.77s-2.99,-7.86 -7,-8.77z",
    "blur": "M6,13c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM6,17c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM6,9c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM6,5c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM10,12.5c-0.83,0 -1.5,0.67 -1.5,1.5s0.67,1.5 1.5,1.5 1.5,-0.67 1.5,-1.5 -0.67,-1.5 -1.5,-1.5zM10,8.5c-0.83,0 -1.5,0.67 -1.5,1.5s0.67,1.5 1.5,1.5 1.5,-0.67 1.5,-1.5 -0.67,-1.5 -1.5,-1.5zM10,17c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM10,7c0.55,0 1,-0.45 1,-1s-0.45,-1 -1,-1 -1,0.45 -1,1 0.45,1 1,1zM14,12.5c-0.83,0 -1.5,0.67 -1.5,1.5s0.67,1.5 1.5,1.5 1.5,-0.67 1.5,-1.5 -0.67,-1.5 -1.5,-1.5zM14,8.5c-0.83,0 -1.5,0.67 -1.5,1.5s0.67,1.5 1.5,1.5 1.5,-0.67 1.5,-1.5 -0.67,-1.5 -1.5,-1.5zM14,17c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM14,7c0.55,0 1,-0.45 1,-1s-0.45,-1 -1,-1 -1,0.45 -1,1 0.45,1 1,1zM18,13c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM18,17c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM18,9c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM18,5c-0.55,0 -1,0.45 -1,1s0.45,1 1,1 1,-0.45 1,-1 -0.45,-1 -1,-1zM3,9.5c-0.28,0 -0.5,0.22 -0.5,0.5s0.22,0.5 0.5,0.5 0.5,-0.22 0.5,-0.5 -0.22,-0.5 -0.5,-0.5zM3,13.5c-0.28,0 -0.5,0.22 -0.5,0.5s0.22,0.5 0.5,0.5 0.5,-0.22 0.5,-0.5 -0.22,-0.5 -0.5,-0.5zM21,9.5c-0.28,0 -0.5,0.22 -0.5,0.5s0.22,0.5 0.5,0.5 0.5,-0.22 0.5,-0.5 -0.22,-0.5 -0.5,-0.5zM21,13.5c-0.28,0 -0.5,0.22 -0.5,0.5s0.22,0.5 0.5,0.5 0.5,-0.22 0.5,-0.5 -0.22,-0.5 -0.5,-0.5z",
    "person": "M12,12c2.21,0 4,-1.79 4,-4s-1.79,-4 -4,-4 -4,1.79 -4,4 1.79,4 4,4zM12,14c-2.67,0 -8,1.34 -8,4v2h16v-2c0,-2.66 -5.33,-4 -8,-4z",
    "image": "M21,19V5c0,-1.1 -0.9,-2 -2,-2H5c-1.1,0 -2,0.9 -2,2v14c0,1.1 0.9,2 2,2h14c1.1,0 2,-0.9 2,-2zM8.5,13.5l2.5,3.01L14.5,12l4.5,6H5l3.5,-4.5z",
    "add": "M19,13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    "power": "M13,3h-2v10h2V3zM17.83,5.17l-1.42,1.42C17.99,7.86 19,9.81 19,12c0,3.87 -3.13,7 -7,7s-7,-3.13 -7,-7c0,-2.19 1.01,-4.14 2.58,-5.42L6.17,5.17C4.23,6.82 3,9.26 3,12c0,4.97 4.03,9 9,9s9,-4.03 9,-9c0,-2.74 -1.23,-5.18 -3.17,-6.83z",
}

LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#16A34A"/><stop offset="1" stop-color="#0E7490"/></linearGradient></defs>'
    '<rect x="4" y="4" width="100" height="100" rx="26" fill="url(#g)"/>'
    '<g transform="translate(30 30) scale(2)">'
    f'<path fill="#fff" d="{ICONS["videocam"]}"/>'
    '<circle cx="10" cy="12" r="2.6" fill="#16A34A"/><circle cx="10" cy="12" r="1.1" fill="#fff"/></g></svg>'
)


def svg_pixmap(svg: str, size: int, dpr: float = 2.0) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(QtCore.Qt.transparent)
    r = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode()))
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon_pixmap(name: str, color: str, size: int = 20) -> QtGui.QPixmap:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="{color}" d="{ICONS[name]}"/></svg>'
    return svg_pixmap(svg, size)


def make_icon(name: str, color: str = C["text"], checked_color: str | None = None, size: int = 20) -> QtGui.QIcon:
    ic = QtGui.QIcon()
    ic.addPixmap(icon_pixmap(name, color, size), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    ic.addPixmap(icon_pixmap(name, C["text3"], size), QtGui.QIcon.Disabled, QtGui.QIcon.Off)
    ic.addPixmap(icon_pixmap(name, checked_color or color, size), QtGui.QIcon.Normal, QtGui.QIcon.On)
    return ic


def app_icon() -> QtGui.QIcon:
    ic = QtGui.QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(svg_pixmap(LOGO_SVG, s, 1.0))
    return ic


STYLE = f"""
* {{ font-family: "Inter", "Segoe UI", "Noto Sans", "Ubuntu", sans-serif; }}
QMainWindow, QWidget#root {{ background: {C['bg']}; }}
QWidget {{ color: {C['text']}; font-size: 13px; }}
QToolTip {{ background: {C['card2']}; color: {C['text']}; border: 1px solid {C['line']}; padding: 6px 8px; border-radius: 6px; }}

QFrame#header {{ background: {C['panel']}; border-bottom: 1px solid {C['line']}; }}
QLabel#appTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#appSub {{ color: {C['text3']}; font-size: 12px; }}
QLabel#pill {{ border-radius: 13px; padding: 0 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#pill[state="idle"] {{ background: {C['card2']}; color: {C['text2']}; }}
QLabel#pill[state="busy"] {{ background: rgba(245,158,11,0.15); color: {C['warn']}; }}
QLabel#pill[state="live"] {{ background: rgba(239,68,68,0.16); color: #ff6b6b; }}
QLabel#pill[state="ok"] {{ background: rgba(34,197,94,0.14); color: {C['accent']}; }}

QFrame#sidebar {{ background: {C['panel']}; border-right: 1px solid {C['line']}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
QFrame#card {{ background: {C['card']}; border: 1px solid {C['line']}; border-radius: 12px; }}
QLabel#cardTitle {{ color: {C['text3']}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#rowLabel {{ color: {C['text2']}; }}
QLabel#hint {{ color: {C['text3']}; font-size: 11px; }}

QPushButton#seg {{ background: transparent; color: {C['text2']}; border: 0; border-radius: 7px; padding: 6px 2px; min-width: 36px; font-weight: 600; }}
QPushButton#seg:hover {{ color: {C['text']}; }}
QPushButton#seg:checked {{ background: {C['accent']}; color: #04130a; }}
QPushButton#seg:disabled {{ color: {C['text3']}; }}
QPushButton#seg:checked:disabled {{ background: {C['accent2']}; color: #0b2a17; }}
QFrame#segBox {{ background: {C['card2']}; border-radius: 9px; }}

QListWidget {{ background: {C['card2']}; border: 0; border-radius: 9px; padding: 4px; outline: 0; }}
QListWidget::item {{ border-radius: 7px; margin: 1px 0; }}
QListWidget::item:selected {{ background: rgba(34,197,94,0.16); }}
QListWidget::item:hover:!selected {{ background: rgba(255,255,255,0.04); }}

QLineEdit, QComboBox {{ background: {C['card2']}; border: 1px solid transparent; border-radius: 8px; padding: 7px 10px; selection-background-color: {C['accent2']}; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {C['accent2']}; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{ background: {C['card2']}; border: 1px solid {C['line']}; selection-background-color: rgba(34,197,94,0.25); outline: 0; padding: 4px; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {C['text3']}; }}

QPushButton#ghost {{ background: {C['card2']}; border: 0; border-radius: 8px; padding: 7px 10px; color: {C['text2']}; }}
QPushButton#ghost:hover {{ color: {C['text']}; background: #232933; }}
QPushButton#connect {{ background: {C['accent']}; color: #04130a; border: 0; border-radius: 10px; padding: 12px; font-size: 14px; font-weight: 700; }}
QPushButton#connect:hover {{ background: #2fd36b; }}
QPushButton#connect:disabled {{ background: {C['card2']}; color: {C['text3']}; }}
QPushButton#connect[live="true"] {{ background: {C['card2']}; color: #ff6b6b; border: 1px solid rgba(239,68,68,0.45); }}
QPushButton#connect[live="true"]:hover {{ background: rgba(239,68,68,0.12); }}

QFrame#toolbar {{ background: rgba(17,20,25,0.92); border: 1px solid {C['line']}; border-radius: 16px; }}
QToolButton#tool {{ background: transparent; border: 0; border-radius: 10px; padding: 7px; }}
QToolButton#tool:hover {{ background: rgba(255,255,255,0.07); }}
QToolButton#tool:checked {{ background: rgba(34,197,94,0.18); }}
QToolButton#tool[danger="true"]:checked {{ background: rgba(239,68,68,0.2); }}
QToolButton#tool:disabled {{ background: transparent; }}
QFrame#vsep {{ background: {C['line']}; }}
QLabel#toolVal {{ color: {C['text2']}; font-size: 12px; font-weight: 600; min-width: 38px; }}

QSlider::groove:horizontal {{ height: 4px; background: {C['line']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {C['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {C['text']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::groove:horizontal:disabled {{ background: {C['card2']}; }}
QSlider::sub-page:horizontal:disabled {{ background: {C['line']}; }}
QSlider::handle:horizontal:disabled {{ background: {C['text3']}; }}
QSlider#exp::sub-page:horizontal {{ background: {C['warn']}; }}

QPushButton#update {{ background: rgba(34,197,94,0.14); color: {C['accent']}; border: 1px solid rgba(34,197,94,0.35); border-radius: 13px; padding: 0 12px; font-size: 12px; font-weight: 700; }}
QPushButton#update:hover {{ background: rgba(34,197,94,0.24); }}
QPushButton#update[mandatory="true"] {{ background: rgba(239,68,68,0.18); color: #ff6b6b; border: 1px solid rgba(239,68,68,0.5); }}
QLabel#danger {{ background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.4); border-radius: 8px; padding: 10px; color: #ffb4b4; }}
QFrame#banner {{ background: rgba(56,189,248,0.10); border: 1px solid rgba(56,189,248,0.35); border-radius: 9px; }}
QLabel#bannerText {{ color: {C['info']}; font-size: 12px; background: transparent; }}
QPushButton#bannerBtn {{ background: {C['info']}; color: #04121a; border: 0; border-radius: 7px; padding: 6px 10px; font-weight: 700; font-size: 12px; }}
QProgressBar {{ background: {C['card2']}; border: 0; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {C['accent']}; border-radius: 4px; }}
QTextBrowser {{ background: {C['card2']}; border: 0; border-radius: 9px; padding: 8px; color: {C['text2']}; }}
QDialog {{ background: {C['panel']}; }}
QFrame#footer {{ background: {C['panel']}; border-top: 1px solid {C['line']}; }}
QLabel#foot {{ color: {C['text3']}; font-size: 12px; }}
QLabel#footStrong {{ color: {C['text2']}; font-size: 12px; font-weight: 600; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['line']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QMessageBox {{ background: {C['panel']}; }}
QMenu {{ background: {C['card']}; border: 1px solid {C['line']}; padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(34,197,94,0.18); }}
"""


# =============================================================================
# Widgets
# =============================================================================

class Toggle(QtWidgets.QAbstractButton):
    """iOS/Material-like switch. Always painted from isChecked(); the slide animation is cosmetic."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._pos = 1.0 if checked else 0.0
        self._anim = QtCore.QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedSize(40, 22)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()
        self._anim_t0 = time.monotonic()
        self.update()
        QtCore.QTimer.singleShot(250, self.update)  # safety repaint if the animation never ticks

    def _get(self) -> float:
        return self._pos

    def _set(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = QtCore.Property(float, _get, _set)  # NOT "pos": that is QWidget.pos (widget position)

    def paintEvent(self, _):
        target = 1.0 if self.isChecked() else 0.0
        running = self._anim.state() == QtCore.QAbstractAnimation.Running
        if running and time.monotonic() - getattr(self, "_anim_t0", 0) > 0.2:
            self._anim.stop()  # stalled animation: never leave the knob in the wrong place
            running = False
        if not running:
            self._pos = target  # also covers setChecked() with blocked signals (synced toggles)
        t = self._pos
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        off, on = QtGui.QColor("#3a414b"), QtGui.QColor(C["accent"])
        track = QtGui.QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QtCore.QRectF(0, 0, 40, 22), 11, 11)
        p.setBrush(QtGui.QColor("#ffffff" if self.isEnabled() else "#9aa1aa"))
        x = 3 + t * 18
        p.drawEllipse(QtCore.QRectF(x, 3, 16, 16))

    def sizeHint(self):
        return QtCore.QSize(40, 22)


class Segmented(QtWidgets.QFrame):
    changed = QtCore.Signal(object)

    def __init__(self, options: list[tuple[str, object]], current=None):
        super().__init__(objectName="segBox")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        self.values = []
        for i, (label, value) in enumerate(options):
            b = QtWidgets.QPushButton(label, objectName="seg", checkable=True)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b, 1)
            self.values.append(value)
        self.set_value(current if current in self.values else self.values[0])
        self.group.idClicked.connect(lambda i: self.changed.emit(self.values[i]))

    def value(self):
        return self.values[max(0, self.group.checkedId())]

    def set_value(self, v) -> None:
        if v in self.values:
            self.group.button(self.values.index(v)).setChecked(True)


class Card(QtWidgets.QFrame):
    def __init__(self, title: str, icon: str | None = None):
        super().__init__(objectName="card")
        self.lay = QtWidgets.QVBoxLayout(self)
        self.lay.setContentsMargins(14, 12, 14, 14)
        self.lay.setSpacing(10)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        if icon:
            ic = QtWidgets.QLabel()
            ic.setPixmap(icon_pixmap(icon, C["text3"], 14))
            head.addWidget(ic)
        head.addWidget(QtWidgets.QLabel(title.upper(), objectName="cardTitle"))
        head.addStretch(1)
        self.head = head
        self.lay.addLayout(head)

    def row(self, label: str, widget: QtWidgets.QWidget, stretch: bool = True) -> None:
        r = QtWidgets.QHBoxLayout()
        r.setSpacing(10)
        lb = QtWidgets.QLabel(label, objectName="rowLabel")
        lb.setFixedWidth(74)
        r.addWidget(lb)
        if stretch:
            r.addWidget(widget, 1)
        else:
            r.addStretch(1)
            r.addWidget(widget)
        self.lay.addLayout(r)


def user_backgrounds_dir() -> Path:
    return E.config_path().parent / "backgrounds"


def builtin_backgrounds() -> list[Path]:
    d = E._bundled_file("assets/backgrounds/01-estudio.jpg")
    return sorted(d.parent.glob("*.jpg")) if d else []


BG_NAMES = {"01-estudio": "Estudio", "02-ventanal": "Ventanal", "03-atardecer": "Atardecer", "04-bokeh": "Bokeh",
            "05-aurora": "Aurora", "06-oceano": "Océano", "07-grafito": "Grafito", "08-pocketlens": "PocketLens"}


class _BigIconMenuStyle(QtWidgets.QProxyStyle):
    """Larger icons in the background picker menu (thumbnails)."""
    def pixelMetric(self, metric, opt=None, widget=None):
        if metric == QtWidgets.QStyle.PM_SmallIconSize:
            return 32
        return super().pixelMetric(metric, opt, widget)


class BgTile(QtWidgets.QAbstractButton):
    """Thumbnail tile of the background gallery (Teams-style)."""
    TW, TH = 72, 44

    def __init__(self, value: str, tip: str, pixmap: QtGui.QPixmap | None = None, icon: str | None = None,
                 removable: bool = False):
        super().__init__()
        self.value, self.pix, self.icon_name, self.removable = value, pixmap, icon, removable
        self.setCheckable(True)
        self.setToolTip(tip)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedSize(self.TW, self.TH)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        r = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        path = QtGui.QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.fillPath(path, QtGui.QColor(C["card2"]))
        if self.pix:
            p.save()
            p.setClipPath(path)
            p.drawPixmap(r.toRect(), self.pix)
            p.restore()
        if self.icon_name:
            col = C["accent"] if self.isChecked() else (C["text"] if self.underMouse() else C["text2"])
            if self.pix:  # icon over thumbnail: darken for contrast
                p.fillPath(path, QtGui.QColor(0, 0, 0, 90))
                col = "#ffffff"
            p.drawPixmap(int(r.center().x() - 10), int(r.center().y() - 10), icon_pixmap(self.icon_name, col, 20))
        if not self.isEnabled():
            p.fillPath(path, QtGui.QColor(0, 0, 0, 120))
        if self.isChecked():
            p.setPen(QtGui.QPen(QtGui.QColor(C["accent"]), 2.5))
        elif self.underMouse():
            p.setPen(QtGui.QPen(QtGui.QColor(C["text2"]), 1.5))
        else:
            p.setPen(QtGui.QPen(QtGui.QColor(C["line"]), 1))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class BgGallery(QtWidgets.QWidget):
    """Grid: blur, built-in backgrounds, user images and an "add" tile. value() is "blur" or an image path."""
    changed = QtCore.Signal(str)
    COLS = 4

    def __init__(self, current: str = "blur"):
        super().__init__()
        self._value = current or "blur"
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 2, 0, 2)
        self.grid.setSpacing(6)
        self.grid.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        self._thumbs: dict[str, QtGui.QPixmap] = {}
        self.rebuild()

    def value(self) -> str:
        return self._value

    def _thumb(self, path: Path) -> QtGui.QPixmap | None:
        key = str(path)
        if key not in self._thumbs:
            rd = QtGui.QImageReader(key)
            rd.setAutoTransform(True)
            sz = rd.size()
            if sz.isValid():
                s = max(BgTile.TW * 2 / sz.width(), BgTile.TH * 2 / sz.height())
                rd.setScaledSize(QtCore.QSize(max(1, int(sz.width() * s)), max(1, int(sz.height() * s))))
            img = rd.read()
            if img.isNull():
                return None
            img = img.copy(QtCore.QRect((img.width() - BgTile.TW * 2) // 2, (img.height() - BgTile.TH * 2) // 2,
                                        BgTile.TW * 2, BgTile.TH * 2))
            self._thumbs[key] = QtGui.QPixmap.fromImage(img)
        return self._thumbs[key]

    def rebuild(self) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                if isinstance(w, QtWidgets.QAbstractButton):
                    self.group.removeButton(w)
                w.hide()
                w.setParent(None)
                w.deleteLater()
        tiles = [BgTile("blur", "Desenfocar fondo", icon="blur")]
        for f in builtin_backgrounds():
            tiles.append(BgTile(str(f), BG_NAMES.get(f.stem, f.stem), self._thumb(f)))
        d = user_backgrounds_dir()
        user = sorted(p for p in d.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")) \
            if d.is_dir() else []
        for f in user:
            pm = self._thumb(f)
            if pm:
                tiles.append(BgTile(str(f), f"Tu imagen: {f.name}", pm, removable=True))
        known = {t.value for t in tiles}
        if self._value not in known:
            if Path(self._value).is_file():  # image chosen outside the gallery folder (old config)
                tiles.append(BgTile(self._value, Path(self._value).name, self._thumb(Path(self._value))))
            else:
                self._value = "blur"
        add = QtWidgets.QToolButton(objectName="tool")
        add.setFixedSize(BgTile.TW, BgTile.TH)
        add.setIcon(make_icon("add", C["text2"]))
        add.setIconSize(QtCore.QSize(20, 20))
        add.setToolTip("Agregar imagen de fondo…")
        add.setCursor(QtCore.Qt.PointingHandCursor)
        add.setStyleSheet(f"QToolButton {{ border: 1px dashed {C['text3']}; border-radius: 8px; background: transparent; }}"
                          f"QToolButton:hover {{ border-color: {C['accent']}; }}")
        add.clicked.connect(self._add)
        for i, t in enumerate(tiles):
            self.group.addButton(t)
            t.setChecked(t.value == self._value)
            t.clicked.connect(lambda _=False, v=t.value: self._select(v))
            if t.removable:
                t.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                t.customContextMenuRequested.connect(lambda _pos, v=t.value: self._remove(v))
            self.grid.addWidget(t, i // self.COLS, i % self.COLS)
        n = len(tiles)
        self.grid.addWidget(add, n // self.COLS, n % self.COLS)

    def _select(self, v: str) -> None:
        self._value = v
        self.changed.emit(v)

    def select(self, v: str) -> None:
        """Programmatic selection (e.g. from the toolbar menu)."""
        for t in self.group.buttons():
            if getattr(t, "value", None) == v:
                t.setChecked(True)
        self._select(v)

    def _add(self) -> None:
        start = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.PicturesLocation) or str(Path.home())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Elegir imagen de fondo", start,
                                                        "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.add_image(path)

    def add_image(self, path: str) -> None:
        """Copy an image into the user's backgrounds folder and select it."""
        src = Path(path)
        if QtGui.QImageReader(str(src)).size().isEmpty():
            QtWidgets.QMessageBox.warning(self, "PocketLens", "No se pudo leer la imagen.")
            return
        d = user_backgrounds_dir()
        d.mkdir(parents=True, exist_ok=True)
        dst = d / src.name
        k = 1
        while dst.exists():
            dst = d / f"{src.stem}-{k}{src.suffix}"
            k += 1
        try:
            import shutil
            shutil.copy2(src, dst)
        except OSError as e:
            QtWidgets.QMessageBox.warning(self, "PocketLens", f"No se pudo copiar la imagen:\n{e}")
            return
        self._value = str(dst)
        self.rebuild()
        self.changed.emit(self._value)

    def _remove(self, v: str) -> None:
        m = QtWidgets.QMenu(self)
        act = m.addAction("Quitar este fondo")
        if m.exec(QtGui.QCursor.pos()) != act:
            return
        try:
            Path(v).unlink()
        except OSError:
            pass
        self._thumbs.pop(v, None)
        was = self._value == v
        if was:
            self._value = "blur"
        self.rebuild()
        if was:
            self.changed.emit(self._value)


class DeviceItem(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, sub: str, dot: str | None):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        ic = QtWidgets.QLabel()
        ic.setPixmap(icon_pixmap(icon, C["text2"], 18))
        lay.addWidget(ic)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(1)
        t = QtWidgets.QLabel(title)
        t.setStyleSheet("font-weight: 600; background: transparent;")
        s = QtWidgets.QLabel(sub)
        s.setStyleSheet(f"color: {C['text3']}; font-size: 11px; background: transparent;")
        col.addWidget(t)
        col.addWidget(s)
        lay.addLayout(col, 1)
        if dot:
            d = QtWidgets.QLabel()
            d.setFixedSize(8, 8)
            d.setStyleSheet(f"background: {dot}; border-radius: 4px;")
            lay.addWidget(d)
        self.setStyleSheet("background: transparent;")


class ToolButton(QtWidgets.QToolButton):
    def __init__(self, icon: str, tip: str, checkable: bool = False, checked_color: str | None = None, danger=False):
        super().__init__(objectName="tool")
        self.setIcon(make_icon(icon, C["text"], checked_color))
        self.setIconSize(QtCore.QSize(20, 20))
        self.setToolTip(tip)
        self.setCheckable(checkable)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setProperty("danger", danger)


class Preview(QtWidgets.QWidget):
    """Video stage: draws the frame (aspect-fit, rounded) + HUD + empty state."""
    double_clicked = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(480, 300)
        self.img: QtGui.QImage | None = None
        self.live = False
        self.stats = ""
        self.person: bool | None = None  # background effect on: person detected?
        self.empty_title = "Sin señal"
        self.empty_sub = "Elige tu teléfono y pulsa Conectar"
        self.logo = svg_pixmap(LOGO_SVG, 72)

    def set_frame(self, arr) -> None:
        h, w = arr.shape[:2]
        self.img = QtGui.QImage(arr.data, w, h, w * 3, QtGui.QImage.Format_RGB888).copy()
        self.update()

    def clear(self) -> None:
        self.img = None
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.double_clicked.emit()

    def _pill(self, p: QtGui.QPainter, x: float, y: float, text: str, bg: QtGui.QColor, fg: QtGui.QColor,
              dot: QtGui.QColor | None = None, right: bool = False) -> None:
        f = QtGui.QFont(self.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        fm = QtGui.QFontMetrics(f)
        w = fm.horizontalAdvance(text) + 24 + (14 if dot else 0)
        h = 28
        if right:
            x -= w
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QtCore.QRectF(x, y, w, h), 14, 14)
        tx = x + 12
        if dot:
            p.setBrush(dot)
            p.drawEllipse(QtCore.QRectF(tx, y + 10, 8, 8))
            tx += 14
        p.setPen(fg)
        p.drawText(QtCore.QRectF(tx, y, w, h), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        r = QtCore.QRectF(self.rect()).adjusted(16, 16, -16, -16)
        path = QtGui.QPainterPath()
        path.addRoundedRect(r, 16, 16)
        p.fillPath(path, QtGui.QColor("#07090b"))
        if self.img is not None:
            iw, ih = self.img.width(), self.img.height()
            s = min(r.width() / iw, r.height() / ih)
            dw, dh = iw * s, ih * s
            target = QtCore.QRectF(r.x() + (r.width() - dw) / 2, r.y() + (r.height() - dh) / 2, dw, dh)
            p.save()
            p.setClipPath(path)
            p.drawImage(target, self.img)
            p.restore()
            if self.live:
                self._pill(p, r.x() + 16, r.y() + 16, "EN VIVO", QtGui.QColor(239, 68, 68, 220), QtGui.QColor("white"),
                           dot=QtGui.QColor("white"))
            if self.person is not None:
                if self.person:
                    self._pill(p, r.x() + 16, r.bottom() - 40, "Persona detectada", QtGui.QColor(0, 0, 0, 150),
                               QtGui.QColor(C["text"]), dot=QtGui.QColor(C["accent"]))
                else:
                    self._pill(p, r.x() + 16, r.bottom() - 40, "Sin persona en cuadro", QtGui.QColor(0, 0, 0, 150),
                               QtGui.QColor(C["text"]), dot=QtGui.QColor(C["warn"]))
            if self.stats:
                self._pill(p, r.right() - 16, r.y() + 16, self.stats, QtGui.QColor(0, 0, 0, 150),
                           QtGui.QColor(C["text"]), right=True)
        else:
            cx, cy = r.center().x(), r.center().y()
            p.drawPixmap(QtCore.QPointF(cx - 36, cy - 70), self.logo)
            f = QtGui.QFont(self.font())
            f.setPixelSize(18)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QtGui.QColor(C["text"]))
            p.drawText(QtCore.QRectF(r.x(), cy + 14, r.width(), 26), QtCore.Qt.AlignCenter, self.empty_title)
            f.setPixelSize(13)
            f.setBold(False)
            p.setFont(f)
            p.setPen(QtGui.QColor(C["text3"]))
            p.drawText(QtCore.QRectF(r.x() + 20, cy + 44, r.width() - 40, 40), QtCore.Qt.AlignHCenter | QtCore.Qt.TextWordWrap,
                       self.empty_sub)
        p.setPen(QtGui.QPen(QtGui.QColor(C["line"]), 1))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)


# =============================================================================
# Main window
# =============================================================================

RES_OPTS = [("480p", "640x480"), ("720p", "1280x720"), ("1080p", "1920x1080")]
FPS_OPTS = [("15", "15"), ("24", "24"), ("30", "30"), ("60", "60")]
QUAL_OPTS = [("Baja", "2"), ("Media", "6"), ("Alta", "10"), ("Máx.", "16")]
def bgfilter_available() -> tuple[bool, str]:
    """Cheap check (no heavy import): AI runtime installed and model bundled."""
    import importlib.util
    for mod in ("mediapipe", "cv2"):
        try:
            if importlib.util.find_spec(mod) is None:
                return False, f"falta el módulo «{mod}» (pip install mediapipe)"
        except (ImportError, ValueError):
            return False, f"falta el módulo «{mod}»"
    if not E._bundled_file("assets/models/selfie_segmenter.tflite"):
        return False, "no se encontró el modelo de segmentación"
    return True, ""


def _preload_bgfilter() -> None:
    try:
        import bgfilter  # noqa: F401
    except Exception:  # noqa: BLE001
        pass


ROT_OPTS = [("0°", "0"), ("90°", "90"), ("180°", "180"), ("270°", "270")]


class Bridge(QtCore.QObject):
    update_found = QtCore.Signal(object)
    task_progress = QtCore.Signal(int)
    task_done = QtCore.Signal(object)
    log = QtCore.Signal(str)
    started = QtCore.Signal(object)
    failed = QtCore.Signal(str)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PocketLens")
        self.setWindowIcon(app_icon())
        self.resize(1280, 780)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self.cfg = self._load_cfg()
        self.adb_path = E.find_adb()
        self.adb = E.Adb(self.adb_path) if self.adb_path else None
        self.video = self.audio = self.poller = None
        self.host = self.serial = None
        self.audio_name = ""
        self.busy = False
        self.quitting = False
        self.tray_hint_shown = False
        self.connected_at = 0.0
        self.last_frame_id = -1
        self.last_status: dict | None = None
        self.bridge = Bridge()
        self.bridge.log.connect(self._busy_msg)
        self.bridge.started.connect(self._on_started)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.update_found.connect(self._on_update_found)
        self.latest: dict | None = None
        self.phone_version = ""
        E.cleanup_old_binary()
        self.discovery = E.Discovery()
        self.discovery.start()

        self._build()
        self._setup_tray()
        self._refresh_usb()
        self._set_state("idle", "DESCONECTADO")
        self.ft["msg"].setText("Listo · F11 pantalla completa · doble clic en la imagen para ampliar")
        self.ft["ver"].setText(f"v{E.APP_VERSION}")
        QtGui.QShortcut(QtGui.QKeySequence("F11"), self, self._toggle_fullscreen)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, lambda: self.isFullScreen() and self._toggle_fullscreen())
        self.timer = QtCore.QTimer(self, interval=33, timeout=self._tick)
        self.timer.start()
        self.slow = QtCore.QTimer(self, interval=1000, timeout=self._slow_tick)
        self.slow.start()
        self.upd_timer = QtCore.QTimer(self, interval=6 * 3600 * 1000, timeout=self._check_updates)
        self.upd_timer.start()
        QtCore.QTimer.singleShot(1500, self._check_updates)

    # ------------------------------------------------------------------ config
    def _load_cfg(self) -> dict:
        try:
            return json.loads(E.config_path().read_text())
        except Exception:  # noqa: BLE001
            return {}

    def _save_cfg(self) -> None:
        c = {
            "mode": self.mode.value(), "ip": self.ed_ip.text().strip(),
            "res": self.seg_res.value(), "fps": self.seg_fps.value(), "bitrate": self.seg_q.value(),
            "camera": self.seg_cam.value(), "rotate": self.seg_rot.value(), "mirror": self.tg_mirror.isChecked(),
            "audio": self.tg_audio.isChecked(), "audio_out": self.cb_aout.currentText(),
            "vdev": self.cb_vdev.currentText() if E.IS_LINUX else "",
            "bg_on": self.tg_bg.isChecked(), "bg_sel": self.gallery.value(), "bg_strength": self.sl_blur.value(),
            "bg_precise": self.seg_prec.value() == "precise",
        }
        try:
            p = E.config_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(c, indent=2))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        c = self.cfg
        root = QtWidgets.QWidget(objectName="root")
        v = QtWidgets.QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = self._build_header()
        v.addWidget(self.header)
        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = self._build_sidebar(c)
        body.addWidget(self.sidebar)
        body.addWidget(self._build_stage(), 1)
        v.addLayout(body, 1)
        self.footer = self._build_footer()
        v.addWidget(self.footer)
        self.setCentralWidget(root)

    def _build_header(self) -> QtWidgets.QFrame:
        h = QtWidgets.QFrame(objectName="header")
        h.setFixedHeight(60)
        lay = QtWidgets.QHBoxLayout(h)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(12)
        logo = QtWidgets.QLabel()
        logo.setPixmap(svg_pixmap(LOGO_SVG, 34))
        lay.addWidget(logo)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(0)
        col.addStretch(1)
        col.addWidget(QtWidgets.QLabel("PocketLens", objectName="appTitle"))
        col.addWidget(QtWidgets.QLabel("Tu teléfono como webcam y micrófono", objectName="appSub"))
        col.addStretch(1)
        lay.addLayout(col)
        lay.addStretch(1)
        self.bt_update = QtWidgets.QPushButton(objectName="update")
        self.bt_update.setFixedHeight(26)
        self.bt_update.setCursor(QtCore.Qt.PointingHandCursor)
        self.bt_update.hide()
        self.bt_update.clicked.connect(self._show_update_dialog)
        lay.addWidget(self.bt_update, 0, QtCore.Qt.AlignVCenter)
        self.pill = QtWidgets.QLabel(objectName="pill")
        self.pill.setFixedHeight(26)
        lay.addWidget(self.pill, 0, QtCore.Qt.AlignVCenter)
        return h

    def _build_sidebar(self, c: dict) -> QtWidgets.QFrame:
        side = QtWidgets.QFrame(objectName="sidebar")
        side.setFixedWidth(384)
        outer = QtWidgets.QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        inner = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(inner)
        lay.setContentsMargins(16, 16, 14, 8)
        lay.setSpacing(12)

        # --- device card
        card = Card("Dispositivo", "phone")
        self.mode = Segmented([("USB", "usb"), ("Wi-Fi", "wifi")], c.get("mode", "usb"))
        self.mode.changed.connect(lambda _: self._mode_changed())
        card.lay.addWidget(self.mode)
        self.dev_stack = QtWidgets.QStackedWidget()
        # usb page
        pu = QtWidgets.QWidget()
        lu = QtWidgets.QVBoxLayout(pu)
        lu.setContentsMargins(0, 0, 0, 0)
        lu.setSpacing(8)
        self.list_usb = QtWidgets.QListWidget()
        self.list_usb.setFixedHeight(108)
        lu.addWidget(self.list_usb)
        rr = QtWidgets.QHBoxLayout()
        self.lb_adb = QtWidgets.QLabel("", objectName="hint")
        self.lb_adb.setWordWrap(True)
        rr.addWidget(self.lb_adb, 1)
        self.bt_refresh = QtWidgets.QPushButton(" Buscar", objectName="ghost")
        self.bt_refresh.setIcon(make_icon("refresh", C["text2"], size=16))
        self.bt_refresh.setCursor(QtCore.Qt.PointingHandCursor)
        self.bt_refresh.clicked.connect(self._refresh_usb)
        rr.addWidget(self.bt_refresh)
        lu.addLayout(rr)
        self.dev_stack.addWidget(pu)
        # wifi page
        pw = QtWidgets.QWidget()
        lw = QtWidgets.QVBoxLayout(pw)
        lw.setContentsMargins(0, 0, 0, 0)
        lw.setSpacing(8)
        self.list_wifi = QtWidgets.QListWidget()
        self.list_wifi.setFixedHeight(108)
        self.list_wifi.itemClicked.connect(lambda it: self.ed_ip.setText(it.data(QtCore.Qt.UserRole) or ""))
        lw.addWidget(self.list_wifi)
        self.ed_ip = QtWidgets.QLineEdit(c.get("ip", ""))
        self.ed_ip.setPlaceholderText("IP manual, p. ej. 192.168.1.50")
        lw.addWidget(self.ed_ip)
        self.dev_stack.addWidget(pw)
        card.lay.addWidget(self.dev_stack)
        self.banner = QtWidgets.QFrame(objectName="banner")
        bl_ = QtWidgets.QHBoxLayout(self.banner)
        bl_.setContentsMargins(10, 8, 8, 8)
        self.banner_text = QtWidgets.QLabel("", objectName="bannerText")
        self.banner_text.setWordWrap(True)
        bl_.addWidget(self.banner_text, 1)
        self.banner_btn = QtWidgets.QPushButton("Actualizar", objectName="bannerBtn")
        self.banner_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.banner_btn.clicked.connect(self._update_phone)
        bl_.addWidget(self.banner_btn)
        self.banner.hide()
        card.lay.addWidget(self.banner)
        lay.addWidget(card)

        # --- background card (Teams/Meet-style effects)
        card = Card("Fondo", "blur")
        sel = c.get("bg_sel") or ("blur" if c.get("bg_mode", "blur") != "image" else (c.get("bg_image") or "blur"))
        self.tg_bg = Toggle(bool(c.get("bg_on", False)))
        self.tg_bg.toggled.connect(lambda on: self.bt_bg.setChecked(on))
        card.row("Efecto", self.tg_bg, stretch=False)
        self.gallery = BgGallery(sel)
        self.gallery.changed.connect(self._bg_selection_changed)
        card.lay.addWidget(self.gallery)
        self.bt_bg_img = QtWidgets.QPushButton("  Usar mi imagen como fondo…", objectName="ghost")
        self.bt_bg_img.setIcon(make_icon("image", C["text2"], size=16))
        self.bt_bg_img.setCursor(QtCore.Qt.PointingHandCursor)
        self.bt_bg_img.setToolTip("Elige una foto de tu PC (también puedes arrastrarla a la ventana)")
        self.bt_bg_img.clicked.connect(self.gallery._add)
        card.lay.addWidget(self.bt_bg_img)
        sr = QtWidgets.QHBoxLayout()
        sr.setSpacing(8)
        self.sl_blur = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_blur.setRange(1, 100)
        self.sl_blur.setValue(int(c.get("bg_strength", 50)))
        self.lb_blur = QtWidgets.QLabel(f"{self.sl_blur.value()}%", objectName="toolVal")
        self.lb_blur.setFixedWidth(36)
        self.sl_blur.valueChanged.connect(self._bg_strength_changed)
        self.sl_blur.sliderReleased.connect(self._save_cfg)
        sr.addWidget(self.sl_blur, 1)
        sr.addWidget(self.lb_blur)
        self.blur_row = QtWidgets.QWidget()
        self.blur_row.setLayout(sr)
        sr.setContentsMargins(0, 0, 0, 0)
        card.row("Intensidad", self.blur_row)
        self.seg_prec = Segmented([("Rápida", "fast"), ("Alta", "precise")],
                                  "precise" if c.get("bg_precise", True) else "fast")
        self.seg_prec.changed.connect(lambda _v: self._apply_bg())
        card.row("Precisión", self.seg_prec)
        hint = QtWidgets.QLabel("Detecta a la persona con IA en este PC y desenfoca o reemplaza el resto. "
                                "Se aplica a la cámara virtual (Meet, Teams, Zoom…). "
                                "Arrastra una imagen a la ventana para usarla de fondo; "
                                "clic derecho en un fondo propio para quitarlo.", objectName="hint")
        hint.setWordWrap(True)
        card.lay.addWidget(hint)
        ok, why = bgfilter_available()
        if not ok:
            for w_ in (self.tg_bg, self.gallery, self.bt_bg_img, self.sl_blur, self.seg_prec):
                w_.setEnabled(False)
            self.tg_bg.blockSignals(True)
            self.tg_bg.setChecked(False)
            self.tg_bg.blockSignals(False)
            hint.setText("Efectos de fondo no disponibles: " + why)
        else:  # warm up the AI runtime in the background so enabling the effect doesn't stall the video
            threading.Thread(target=_preload_bgfilter, daemon=True, name="bg-preload").start()
        self._bg_ok = ok
        self.blur_row.setEnabled(ok and self.gallery.value() == "blur")
        lay.addWidget(card)

        # --- video card
        card = Card("Vídeo", "videocam")
        self.seg_cam = Segmented([("Trasera", "back"), ("Frontal", "front")], c.get("camera", "back"))
        self.seg_res = Segmented(RES_OPTS, c.get("res", "1280x720"))
        self.seg_fps = Segmented(FPS_OPTS, c.get("fps", "30"))
        self.seg_q = Segmented(QUAL_OPTS, c.get("bitrate", "6"))
        card.row("Cámara", self.seg_cam)
        card.row("Resolución", self.seg_res)
        card.row("FPS", self.seg_fps)
        card.row("Calidad", self.seg_q)
        lay.addWidget(card)

        # --- image card
        card = Card("Imagen", "camera")
        self.seg_rot = Segmented(ROT_OPTS, str(c.get("rotate", "0")))
        card.row("Rotación", self.seg_rot)
        self.tg_mirror = Toggle(bool(c.get("mirror", False)))
        self.tg_mirror.toggled.connect(lambda on: self.bt_mirror.setChecked(on))
        card.row("Espejo", self.tg_mirror, stretch=False)
        self.cb_vdev = QtWidgets.QComboBox()
        if E.IS_LINUX:
            self._fill_vdevs(c.get("vdev"))
            card.row("Dispositivo", self.cb_vdev)
        lay.addWidget(card)

        # --- audio card
        card = Card("Audio", "mic")
        self.tg_audio = Toggle(bool(c.get("audio", True)))
        self.tg_audio.toggled.connect(self._audio_toggled)
        card.row("Micrófono", self.tg_audio, stretch=False)
        self.cb_aout = QtWidgets.QComboBox()
        if E.pipewire_available():
            self.cb_aout.addItem("Micrófono virtual “Android Mic”", None)
        for idx, name in E.output_devices():
            self.cb_aout.addItem(name, idx)
        if self.cb_aout.count() == 0:
            self.cb_aout.addItem("Sin salida disponible", -1)
        want = c.get("audio_out")
        i = self.cb_aout.findText(want) if want else -1
        if i < 0 and E.IS_WIN:
            i = next((k for k in range(self.cb_aout.count()) if "CABLE Input" in self.cb_aout.itemText(k)), -1)
        if i >= 0:
            self.cb_aout.setCurrentIndex(i)
        card.row("Salida", self.cb_aout)
        if E.IS_WIN:
            hint = QtWidgets.QLabel("Usa VB-Cable: elige «CABLE Input» aquí y «CABLE Output» como micrófono en tu app.",
                                    objectName="hint")
            hint.setWordWrap(True)
            card.lay.addWidget(hint)
        lay.addWidget(card)
        lay.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        bottom = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(bottom)
        bl.setContentsMargins(16, 10, 16, 16)
        self.bt_connect = QtWidgets.QPushButton("Conectar", objectName="connect")
        self.bt_connect.setCursor(QtCore.Qt.PointingHandCursor)
        self.bt_connect.setIcon(make_icon("power", "#04130a", size=18))
        self.bt_connect.clicked.connect(self._toggle)
        bl.addWidget(self.bt_connect)
        outer.addWidget(bottom)

        self.settings_widgets = [self.mode, self.list_usb, self.bt_refresh, self.list_wifi, self.ed_ip, self.seg_cam,
                                 self.seg_res, self.seg_fps, self.seg_q, self.seg_rot, self.cb_vdev,
                                 self.cb_aout]
        self._mode_changed()
        return side

    def _build_stage(self) -> QtWidgets.QWidget:
        stage = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(stage)
        g.setContentsMargins(0, 0, 0, 0)
        self.preview = Preview()
        self.preview.double_clicked.connect(self._toggle_fullscreen)
        g.addWidget(self.preview, 0, 0)

        tb = QtWidgets.QFrame(objectName="toolbar")
        tl = QtWidgets.QHBoxLayout(tb)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(4)
        self.bt_switch = ToolButton("switch", "Cambiar cámara")
        self.bt_switch.clicked.connect(lambda: self._api("/api/switch"))
        self.bt_torch = ToolButton("flash", "Linterna", True, C["warn"])
        self.bt_torch.clicked.connect(lambda: self._api("/api/torch"))
        self.bt_mic = ToolButton("mic", "Silenciar micrófono", True, danger=True)
        self.bt_mic.setIcon(self._mic_icon())
        self.bt_mic.clicked.connect(lambda: self._api("/api/mic"))
        for b in (self.bt_switch, self.bt_torch, self.bt_mic):
            tl.addWidget(b)
        tl.addWidget(self._vsep())
        zi = QtWidgets.QLabel()
        zi.setPixmap(icon_pixmap("zoom", C["text2"], 18))
        tl.addWidget(zi)
        self.sl_zoom = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_zoom.setFixedWidth(120)
        self.sl_zoom.valueChanged.connect(self._zoom_changed)
        tl.addWidget(self.sl_zoom)
        self.lb_zoom = QtWidgets.QLabel("1.0×", objectName="toolVal")
        tl.addWidget(self.lb_zoom)
        ei = QtWidgets.QLabel()
        ei.setPixmap(icon_pixmap("exposure", C["text2"], 18))
        tl.addWidget(ei)
        self.sl_exp = QtWidgets.QSlider(QtCore.Qt.Horizontal, objectName="exp")
        self.sl_exp.setFixedWidth(110)
        self.sl_exp.valueChanged.connect(self._exp_changed)
        tl.addWidget(self.sl_exp)
        self.lb_exp = QtWidgets.QLabel("0", objectName="toolVal")
        tl.addWidget(self.lb_exp)
        tl.addWidget(self._vsep())
        self.bt_mirror = ToolButton("flip", "Espejo (salida)", True, C["accent"])
        self.bt_mirror.setChecked(self.tg_mirror.isChecked())
        self.bt_mirror.toggled.connect(self._mirror_changed)
        self.bt_bg = ToolButton("blur", "Efecto de fondo (detección de personas)", True, C["accent"])
        self.bt_bg.setChecked(self.tg_bg.isChecked())
        self.bt_bg.setEnabled(self._bg_ok)
        self.bt_bg.toggled.connect(self._bg_toggled)
        self.bt_bg_menu = ToolButton("image", "Cambiar fondo: desenfoque, fondos o tu propia imagen")
        self.bt_bg_menu.setEnabled(self._bg_ok)
        self.bt_bg_menu.clicked.connect(self._bg_menu)
        self.bt_snap = ToolButton("camera", "Foto")
        self.bt_snap.clicked.connect(self._snapshot)
        self.bt_full = ToolButton("fullscreen", "Pantalla completa (F11)")
        self.bt_full.clicked.connect(self._toggle_fullscreen)
        for b in (self.bt_mirror, self.bt_bg, self.bt_bg_menu, self.bt_snap, self.bt_full):
            tl.addWidget(b)
        shadow = QtWidgets.QGraphicsDropShadowEffect(blurRadius=24, offset=QtCore.QPointF(0, 6))
        shadow.setColor(QtGui.QColor(0, 0, 0, 160))
        tb.setGraphicsEffect(shadow)
        self.toolbar = tb
        holder = QtWidgets.QWidget()
        holder.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        hl = QtWidgets.QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 34)
        hl.addWidget(tb)
        g.addWidget(holder, 0, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter)
        self._set_controls_enabled(False)
        return stage

    def _vsep(self) -> QtWidgets.QFrame:
        s = QtWidgets.QFrame(objectName="vsep")
        s.setFixedSize(1, 22)
        return s

    def _mic_icon(self) -> QtGui.QIcon:
        ic = QtGui.QIcon()
        ic.addPixmap(icon_pixmap("mic", C["text"]), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        ic.addPixmap(icon_pixmap("mic_off", "#ff6b6b"), QtGui.QIcon.Normal, QtGui.QIcon.On)
        ic.addPixmap(icon_pixmap("mic", C["text3"]), QtGui.QIcon.Disabled, QtGui.QIcon.Off)
        return ic

    def _build_footer(self) -> QtWidgets.QFrame:
        f = QtWidgets.QFrame(objectName="footer")
        f.setFixedHeight(34)
        lay = QtWidgets.QHBoxLayout(f)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(18)
        self.ft = {}
        self.ft_icons = []
        for key, icon in (("msg", None), ("vcam", "videocam"), ("audio", "speaker"), ("fps", None), ("up", None), ("ver", None)):
            box = QtWidgets.QHBoxLayout()
            box.setSpacing(6)
            if icon:
                ic = QtWidgets.QLabel()
                ic.setPixmap(icon_pixmap(icon, C["text3"], 14))
                ic.hide()
                self.ft_icons.append(ic)
                box.addWidget(ic)
            lb = QtWidgets.QLabel("", objectName="footStrong" if key == "fps" else "foot")
            box.addWidget(lb)
            self.ft[key] = lb
            lay.addLayout(box)
            if key == "msg":
                lay.addStretch(1)
        return f

    def _setup_tray(self) -> None:
        self.tray = None
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QtWidgets.QSystemTrayIcon(app_icon(), self)
        m = QtWidgets.QMenu()
        m.addAction("Mostrar ventana", self._show_window)
        self.act_connect = m.addAction("Conectar", self._toggle)
        m.addSeparator()
        m.addAction("Salir", self._quit)
        self.tray.setContextMenu(m)
        self.tray.setToolTip("PocketLens")
        self.tray.activated.connect(lambda r: r == QtWidgets.QSystemTrayIcon.Trigger and self._show_window())
        self.tray.show()

    # ------------------------------------------------------------------ helpers
    def _fill_vdevs(self, want: str | None = None) -> None:
        self.cb_vdev.clear()
        devs = E.loopback_devices()
        for d, name in devs:
            self.cb_vdev.addItem(f"{d}  ·  {name}", d)
        if not devs:
            self.cb_vdev.addItem("No disponible — se cargará al conectar", None)
        for i in range(self.cb_vdev.count()):
            if self.cb_vdev.itemData(i) == want:
                self.cb_vdev.setCurrentIndex(i)

    def _set_state(self, state: str, text: str) -> None:
        self.pill.setProperty("state", state)
        self.pill.setText(("●  " if state in ("live", "ok") else "") + text)
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)
        if self.tray:
            self.tray.setToolTip(f"PocketLens — {text.capitalize()}")

    def _busy_msg(self, msg: str) -> None:
        self.ft["msg"].setText(msg)
        self.preview.empty_title = "Conectando…"
        self.preview.empty_sub = msg
        self.preview.update()

    def _mode_changed(self) -> None:
        self.dev_stack.setCurrentIndex(0 if self.mode.value() == "usb" else 1)

    def _refresh_usb(self) -> None:
        self.list_usb.clear()
        if not self.adb:
            self.lb_adb.setText("adb no encontrado. Instala platform-tools o ponlo junto al programa.")
            return
        devs = self.adb.devices()
        for serial, state, model in devs:
            ok = state == "device"
            sub = serial if ok else f"{serial} · {'autoriza en el teléfono' if state == 'unauthorized' else state}"
            it = QtWidgets.QListWidgetItem()
            it.setData(QtCore.Qt.UserRole, serial if ok else None)
            w = DeviceItem("usb", model.replace("_", " ") or "Android", sub, C["accent"] if ok else C["warn"])
            it.setSizeHint(QtCore.QSize(0, 48))
            self.list_usb.addItem(it)
            self.list_usb.setItemWidget(it, w)
        if self.list_usb.count():
            self.list_usb.setCurrentRow(0)
        self.lb_adb.setText(f"{len(devs)} dispositivo(s) por USB" if devs else
                            "Conecta el teléfono y activa la depuración USB.")

    def _refresh_wifi(self) -> None:
        phones = self.discovery.phones()
        ips = [ip for ip, _ in phones]
        current = [self.list_wifi.item(i).data(QtCore.Qt.UserRole) for i in range(self.list_wifi.count())]
        if ips == current:
            return
        sel = self.ed_ip.text().strip()
        self.list_wifi.clear()
        for ip, m in phones:
            it = QtWidgets.QListWidgetItem()
            it.setData(QtCore.Qt.UserRole, ip)
            w = DeviceItem("wifi", m.get("name", "Android"), ip + ("  ·  en uso" if m.get("live") else ""),
                           C["live"] if m.get("live") else C["accent"])
            it.setSizeHint(QtCore.QSize(0, 48))
            self.list_wifi.addItem(it)
            self.list_wifi.setItemWidget(it, w)
            if ip == sel:
                it.setSelected(True)
        if not phones:
            it = QtWidgets.QListWidgetItem("  Buscando teléfonos en la red…")
            it.setFlags(QtCore.Qt.NoItemFlags)
            it.setForeground(QtGui.QColor(C["text3"]))
            self.list_wifi.addItem(it)
        if not sel and phones:
            self.ed_ip.setText(phones[0][0])

    def _set_controls_enabled(self, on: bool) -> None:
        for w in (self.bt_switch, self.bt_torch, self.bt_mic, self.sl_zoom, self.sl_exp, self.bt_snap):
            w.setEnabled(on)
        self.toolbar.setVisible(on)

    def _set_inputs_enabled(self, on: bool) -> None:
        for w in self.settings_widgets:
            w.setEnabled(on)

    def _api(self, path: str, params: dict | None = None) -> None:
        host = self.host
        if host:
            threading.Thread(target=E.phone_api, args=(host, path, params), daemon=True).start()

    def _zoom_changed(self, v: int) -> None:
        self.lb_zoom.setText(f"{v / 10:.1f}×")
        if self.sl_zoom.isSliderDown() or not self._syncing:
            self._api("/api/zoom", {"v": v / 10})

    def _exp_changed(self, v: int) -> None:
        self.lb_exp.setText(f"{v:+d}" if v else "0")
        if self.sl_exp.isSliderDown() or not self._syncing:
            self._api("/api/exposure", {"v": v})

    _syncing = False

    def _mirror_changed(self, on: bool) -> None:
        self.tg_mirror.blockSignals(True)
        self.tg_mirror.setChecked(on)
        self.tg_mirror.blockSignals(False)
        if self.video:
            self.video.mirror = on

    # drag & drop an image anywhere on the window → background
    @staticmethod
    def _dropped_image(e) -> str | None:
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                f = u.toLocalFile()
                if f and Path(f).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                    return f
        return None

    def dragEnterEvent(self, e):
        if self._bg_ok and self._dropped_image(e):
            e.acceptProposedAction()

    def dropEvent(self, e):
        f = self._dropped_image(e)
        if f and self._bg_ok:
            e.acceptProposedAction()
            self.gallery.add_image(f)

    def _bg_menu(self) -> None:
        """Teams-like quick picker on the floating toolbar."""
        m = QtWidgets.QMenu(self)
        if not hasattr(self, "_menu_style"):
            self._menu_style = _BigIconMenuStyle("Fusion")
        m.setStyle(self._menu_style)
        on, cur = self.bt_bg.isChecked(), self.gallery.value()

        def add(text, value, icon=None):
            a = m.addAction(icon or QtGui.QIcon(), text)
            a.setCheckable(True)
            a.setChecked(on and value == cur if value else not on)
            a.setData(value)
            return a

        add("Sin efecto", "")
        add("Desenfocar fondo", "blur", make_icon("blur", C["text2"]))
        m.addSeparator()
        for t in self.gallery.group.buttons():
            if t.value == "blur" or not t.pix:
                continue
            name = t.toolTip()
            add(name, t.value, QtGui.QIcon(t.pix))
        m.addSeparator()
        pick = m.addAction(make_icon("add", C["accent"]), "Elegir imagen de mi PC…")
        a = m.exec(self.bt_bg_menu.mapToGlobal(QtCore.QPoint(0, -m.sizeHint().height() - 6)))
        if a is None:
            return
        if a is pick:
            self.gallery._add()
            return
        v = a.data()
        if not v:
            self.bt_bg.setChecked(False)
            return
        self.gallery.select(v)

    def _bg_toggled(self, on: bool) -> None:
        self.tg_bg.blockSignals(True)
        self.tg_bg.setChecked(on)
        self.tg_bg.blockSignals(False)
        self._apply_bg()

    def _bg_selection_changed(self, _sel) -> None:
        self.blur_row.setEnabled(self._bg_ok and self.gallery.value() == "blur")
        if self._bg_ok and not self.bt_bg.isChecked():
            self.bt_bg.setChecked(True)  # picking a background turns the effect on (like Teams)
        else:
            self._apply_bg()

    def _bg_strength_changed(self, v: int) -> None:
        self.lb_blur.setText(f"{v}%")
        if self.video:
            self.video.bg_strength = v
        if not self.sl_blur.isSliderDown():
            self._save_cfg()

    def _apply_bg(self) -> None:
        on = self._bg_ok and self.bt_bg.isChecked()
        sel = self.gallery.value()
        if self.video:
            self.video.bg_strength = self.sl_blur.value()
            self.video.bg_precise = self.seg_prec.value() == "precise"
            self.video.bg_image = None if sel == "blur" else sel
            self.video.bg_mode = ("blur" if sel == "blur" else "image") if on else None
        if not on:
            self.preview.person = None
            self.preview.update()
        self._save_cfg()

    def _snapshot(self) -> None:
        if not self.video or self.video.latest is None:
            return
        f = self.video.latest
        img = QtGui.QImage(f.data, f.shape[1], f.shape[0], f.shape[1] * 3, QtGui.QImage.Format_RGB888).copy()
        pics = Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.PicturesLocation) or Path.home())
        path = pics / time.strftime("webcam-%Y%m%d-%H%M%S.png")
        img.save(str(path))
        self.ft["msg"].setText(f"Foto guardada en {path}")

    def _toggle_fullscreen(self) -> None:
        full = not self.isFullScreen()
        for w in (self.header, self.sidebar, self.footer):
            w.setVisible(not full)
        if full:
            self.showFullScreen()
        else:
            self.showNormal()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self.quitting = True
        self.close()

    # ------------------------------------------------------------------ connect
    def _toggle(self) -> None:
        if self.busy:
            return
        if self.video:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        if E.is_mandatory(self.latest):
            self._show_update_dialog()
            return
        self._save_cfg()
        usb = self.mode.value() == "usb"
        if usb:
            if not self.adb:
                return self._warn("No se encontró adb. Instala Android platform-tools o pon la carpeta "
                                  "«platform-tools» junto a este programa.")
            it = self.list_usb.currentItem()
            serial = it.data(QtCore.Qt.UserRole) if it else None
            if not serial:
                self._refresh_usb()
                it = self.list_usb.currentItem()
                serial = it.data(QtCore.Qt.UserRole) if it else None
            if not serial:
                return self._warn("Conecta el teléfono por USB, activa la depuración USB y acepta "
                                  "«Permitir depuración USB» en el teléfono.")
            self.serial, ip = serial, None
        else:
            ip = self.ed_ip.text().strip()
            if not ip:
                return self._warn("Elige un teléfono detectado o escribe la IP que muestra la app.")
            self.serial = None

        vdev = None
        if E.IS_LINUX:
            if not E.loopback_devices():
                r = QtWidgets.QMessageBox.question(
                    self, "Cámara virtual", "Para crear la cámara virtual hay que cargar el módulo "
                    "v4l2loopback (pedirá tu contraseña).\n\n¿Cargarlo ahora?")
                if r != QtWidgets.QMessageBox.Yes:
                    return
                if not E.load_loopback_module():
                    return self._warn("No se pudo cargar v4l2loopback.\nInstálalo con: sudo apt install v4l2loopback-dkms")
                time.sleep(1)
                self._fill_vdevs()
            vdev = E.prepare_loopback(self.cb_vdev.currentData())
            if not vdev:
                return self._warn("No se encontró un dispositivo v4l2loopback.")

        params = {"camera": self.seg_cam.value(), "res": self.seg_res.value(), "fps": self.seg_fps.value(),
                  "bitrate": self.seg_q.value(), "audio": "1" if self.tg_audio.isChecked() else "0"}
        self.busy = True
        self.bt_connect.setEnabled(False)
        self.bt_connect.setText("Conectando…")
        self._set_inputs_enabled(False)
        self._set_state("busy", "CONECTANDO")
        threading.Thread(target=self._connect_bg, args=(usb, ip, params, vdev), daemon=True).start()

    def _connect_bg(self, usb: bool, ip: str | None, params: dict, vdev: str | None) -> None:
        log = self.bridge.log.emit
        try:
            if usb:
                a, s = self.adb, self.serial
                if E.PKG not in a.run("shell", "pm", "path", E.PKG, serial=s).stdout:
                    apk = E.find_apk()
                    if not apk:
                        raise RuntimeError("La app no está instalada en el teléfono y no se encontró WebCam.apk.")
                    log("Instalando la app en el teléfono…")
                    r = a.run("install", "-r", str(apk), serial=s, timeout=180)
                    if r.returncode != 0:
                        raise RuntimeError("Error instalando la app: " + (r.stderr or r.stdout).strip())
                for perm in ("CAMERA", "RECORD_AUDIO", "POST_NOTIFICATIONS"):
                    a.run("shell", "pm", "grant", E.PKG, f"android.permission.{perm}", serial=s)
                log("Preparando conexión USB…")
                for p in (E.PORT_VIDEO, E.PORT_AUDIO, E.PORT_HTTP):
                    r = a.run("forward", f"tcp:{p}", f"tcp:{p}", serial=s)
                    if r.returncode != 0:
                        raise RuntimeError(f"No se pudo redirigir el puerto {p} (¿ocupado en este PC?).\n{r.stderr.strip()}")
                a.run("shell", "input", "keyevent", "KEYCODE_WAKEUP", serial=s)
                log("Abriendo la app en el teléfono…")
                a.run("shell", "am", "start", "-n", f"{E.PKG}/.MainActivity", serial=s)
                host = "127.0.0.1"
            else:
                host = ip
            log("Esperando respuesta del teléfono…")
            st = None
            for _ in range(30):
                st = E.phone_api(host, "/api/status", timeout=1.5)
                if st:
                    break
                time.sleep(0.5)
            if not st:
                raise RuntimeError("El teléfono no responde. Abre la app PocketLens" +
                                   ("." if usb else " y comprueba que ambos estén en la misma red Wi-Fi."))
            E.phone_api(host, "/api/config", params)
            self.bridge.started.emit({"host": host, "params": params, "vdev": vdev, "model": st.get("model", "")})
        except Exception as e:  # noqa: BLE001
            self.bridge.failed.emit(str(e))

    def _warn(self, msg: str) -> None:
        QtWidgets.QMessageBox.warning(self, "PocketLens", msg)

    def _on_failed(self, msg: str) -> None:
        self.busy = False
        self.bt_connect.setEnabled(True)
        self.bt_connect.setText("Conectar")
        self._set_inputs_enabled(True)
        self._set_state("idle", "DESCONECTADO")
        self.preview.empty_title = "No se pudo conectar"
        self.preview.empty_sub = msg
        self.preview.update()
        self.ft["msg"].setText("Error de conexión")
        self._warn(msg)

    def _on_started(self, info: dict) -> None:
        self.host = info["host"]
        w, h = (int(x) for x in info["params"]["res"].split("x"))
        self.video = E.VideoWorker(self.host, w, h, int(info["params"]["fps"]), int(self.seg_rot.value()),
                                   self.bt_mirror.isChecked(), info["vdev"])
        self._apply_bg()
        self.video.start()
        self.audio, self.audio_name = None, ""
        if self.tg_audio.isChecked():
            self._start_audio()
        self.poller = E.StatusPoller(self.host)
        self.poller.start()
        self.busy = False
        self.connected_at = time.monotonic()
        self.model = info.get("model", "")
        self.bt_connect.setEnabled(True)
        self.bt_connect.setText("Desconectar")
        self.bt_connect.setIcon(make_icon("power", "#ff6b6b", size=18))
        self.bt_connect.setProperty("live", True)
        self.bt_connect.style().unpolish(self.bt_connect)
        self.bt_connect.style().polish(self.bt_connect)
        if self.tray:
            self.act_connect.setText("Desconectar")
        self._set_controls_enabled(True)
        for ic in self.ft_icons:
            ic.show()
        self.ft["msg"].setText(f"Conectado a {self.model or self.host}")

    def _start_audio(self) -> None:
        try:
            data = self.cb_aout.currentData()
            sink = None
            if data is None and E.pipewire_available():
                sink = E.PipeWireSource()
            elif data is not None and data >= 0 and E.sd is not None:
                sink = E.SoundDeviceSink(data)
            if sink:
                self.audio_name = sink.name
                self.audio = E.AudioWorker(self.host, sink)
                self.audio.start()
        except Exception as e:  # noqa: BLE001
            self.ft["msg"].setText(f"Audio desactivado: {e}")

    def _audio_toggled(self, on: bool) -> None:
        """Microphone can be switched on/off while connected (no reconnect needed)."""
        self._save_cfg()
        if not self.video:  # not connected: applies on next connect
            return
        if on and not self.audio:
            self._start_audio()
        elif not on and self.audio:
            a, self.audio, self.audio_name = self.audio, None, ""
            a.stop()
            a.join(3)
        self.cb_aout.setEnabled(not self.audio)

    def _disconnect(self) -> None:
        for wk in (self.video, self.audio):
            if wk:
                wk.stop()
        if self.poller:
            self.poller.stop_ev.set()
        for wk in (self.video, self.audio):
            if wk:
                wk.join(4)
        if self.adb and self.serial:
            for p in (E.PORT_VIDEO, E.PORT_AUDIO, E.PORT_HTTP):
                self.adb.run("forward", "--remove", f"tcp:{p}", serial=self.serial)
        self.video = self.audio = self.poller = None
        self.last_status = None
        self.bt_connect.setText("Conectar")
        self.bt_connect.setIcon(make_icon("power", "#04130a", size=18))
        self.bt_connect.setProperty("live", False)
        self.bt_connect.style().unpolish(self.bt_connect)
        self.bt_connect.style().polish(self.bt_connect)
        if self.tray:
            self.act_connect.setText("Conectar")
        self._set_controls_enabled(False)
        self._set_inputs_enabled(True)
        self._set_state("idle", "DESCONECTADO")
        self.preview.clear()
        self.preview.live = False
        self.preview.empty_title = "Sin señal"
        self.preview.empty_sub = "Elige tu teléfono y pulsa Conectar"
        self.banner.hide()
        for k in ("vcam", "audio", "fps", "up"):
            self.ft[k].setText("")
        for ic in self.ft_icons:
            ic.hide()
        self.ft["msg"].setText("Desconectado")

    # ------------------------------------------------------------------ ticks
    def _tick(self) -> None:
        v = self.video
        if not v:
            return
        if v.error:
            err, v.error = v.error, None
            self._disconnect()
            self._warn(err)
            return
        if v.bg_error:
            err, v.bg_error = v.bg_error, None
            self.bt_bg.setChecked(False)
            self._warn("No se pudo aplicar el efecto de fondo:\n\n" + err)
        if v.frame_id != self.last_frame_id and v.latest is not None:
            self.last_frame_id = v.frame_id
            self.preview.person = v.person
            self.preview.set_frame(v.latest)
        elif not v.connected and self.preview.img is None:
            self.preview.empty_title = "Esperando vídeo…"
            self.preview.empty_sub = v.state
            self.preview.update()

    def _slow_tick(self) -> None:
        self._refresh_wifi()
        v = self.video
        if not v:
            return
        st = self.poller.status if self.poller else None
        self.last_status = st
        if v.connected:
            self._set_state("live", "EN VIVO")
        else:
            self._set_state("busy", "RECONECTANDO")
        self.preview.live = v.connected
        if st:
            self.phone_version = st.get("version", "")
            if self._check_phone_mandatory():
                return
            self._update_phone_banner()
            self.preview.stats = (f"{'Frontal' if st.get('camera') == 'front' else 'Trasera'}  ·  "
                                  f"{st['width']}×{st['height']}  ·  {v.stat_fps:.0f} fps  ·  {st['kbps'] / 1000:.1f} Mbps")
            self.bt_torch.setEnabled(bool(st.get("hasFlash")))
            self.bt_torch.setChecked(bool(st.get("torch")))
            self.bt_mic.setEnabled(bool(st.get("audioEnabled", True)))
            self.bt_mic.setChecked(bool(st.get("muted")))
            self._syncing = True
            if not self.sl_zoom.isSliderDown():
                self.sl_zoom.blockSignals(True)
                self.sl_zoom.setRange(int(st["minZoom"] * 10), int(st["maxZoom"] * 10))
                self.sl_zoom.setValue(int(round(st["zoom"] * 10)))
                self.lb_zoom.setText(f"{st['zoom']:.1f}×")
                self.sl_zoom.blockSignals(False)
            if not self.sl_exp.isSliderDown():
                self.sl_exp.blockSignals(True)
                self.sl_exp.setRange(int(st["expMin"]), int(st["expMax"]))
                self.sl_exp.setValue(int(st["exposure"]))
                self.lb_exp.setText(f"{st['exposure']:+d}" if st["exposure"] else "0")
                self.sl_exp.blockSignals(False)
            self._syncing = False
        self.ft["vcam"].setText(v.cam_name or "—")
        if self.audio:
            self.ft["audio"].setText(self.audio_name + ("" if self.audio.connected else " (sin señal)"))
        else:
            self.ft["audio"].setText("Audio desactivado")
        self.ft["fps"].setText(f"{v.stat_fps:.0f} fps" if v.connected else "")
        up = int(time.monotonic() - self.connected_at)
        self.ft["up"].setText(f"{up // 3600:02d}:{up % 3600 // 60:02d}:{up % 60:02d}")

    # ------------------------------------------------------------------ updates
    def _check_updates(self) -> None:
        threading.Thread(target=lambda: self.bridge.update_found.emit(E.latest_release()), daemon=True).start()

    def _on_update_found(self, rel: dict | None) -> None:
        if not rel:
            return
        self.latest = rel
        mandatory = E.is_mandatory(rel)
        self.bt_update.setProperty("mandatory", mandatory)
        self.bt_update.style().unpolish(self.bt_update)
        self.bt_update.style().polish(self.bt_update)
        if mandatory:
            self.bt_update.setText("⚠  Actualización de seguridad obligatoria")
            self.bt_update.show()
            if self.video:
                self._disconnect()
            QtCore.QTimer.singleShot(0, self._show_update_dialog)
        elif E.is_newer(rel["version"], E.APP_VERSION):
            self.bt_update.setText(f"⬆  Actualizar a v{rel['version']}")
            self.bt_update.show()
            if self.tray:
                self.tray.showMessage("PocketLens", f"Hay una nueva versión: v{rel['version']}", app_icon(), 5000)
        else:
            self.bt_update.hide()
        self._update_phone_banner()

    def _check_phone_mandatory(self) -> bool:
        """Disconnects and asks to update if the phone app is below the minimum supported version."""
        rel = self.latest
        if not (self.video and self.phone_version and E.is_mandatory(rel, self.phone_version)):
            return False
        serial = self.serial
        self._disconnect()
        if serial and self.adb and E.pick_asset(rel["assets"], "apk"):
            r = QtWidgets.QMessageBox.warning(
                self, "Actualización obligatoria del teléfono",
                f"La app del teléfono (v{self.phone_version}) tiene un problema de seguridad conocido.\n"
                f"Hay que actualizarla a v{rel['version']} para usarla. ¿Actualizar ahora por USB?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
            if r == QtWidgets.QMessageBox.Yes:
                self.serial = serial
                self._update_phone(skip_disconnect=True)
        else:
            self._warn(f"La app del teléfono (v{self.phone_version}) tiene un problema de seguridad conocido.\n"
                       "Ábrela en el teléfono y acepta la actualización obligatoria.")
        return True

    def _update_phone_banner(self) -> None:
        rel = self.latest
        show = bool(rel and self.video and self.serial and self.phone_version
                    and E.is_newer(rel["version"], self.phone_version) and E.pick_asset(rel["assets"], "apk"))
        if show:
            self.banner_text.setText(f"App del teléfono v{self.phone_version} → v{rel['version']} disponible")
        self.banner.setVisible(show)

    def _progress_dialog(self, title: str, text: str) -> tuple[QtWidgets.QDialog, QtWidgets.QProgressBar, QtWidgets.QLabel]:
        d = QtWidgets.QDialog(self)
        d.setWindowTitle(title)
        d.setModal(True)
        d.setFixedWidth(420)
        v = QtWidgets.QVBoxLayout(d)
        v.setContentsMargins(20, 18, 20, 18)
        lb = QtWidgets.QLabel(text)
        lb.setWordWrap(True)
        v.addWidget(lb)
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setFixedHeight(8)
        v.addWidget(bar)
        return d, bar, lb

    def _run_task(self, fn, title: str, text: str, on_done) -> None:
        """Runs fn(progress_cb) in a thread with a modal progress dialog; on_done(result_or_exception)."""
        d, bar, _ = self._progress_dialog(title, text)
        br = Bridge()
        br.task_progress.connect(bar.setValue)

        def finished(res):
            d.accept()
            on_done(res)
        br.task_done.connect(finished)

        def work():
            try:
                res = fn(br.task_progress.emit)
            except Exception as e:  # noqa: BLE001
                res = e
            br.task_done.emit(res)
        self._task_bridge = br
        threading.Thread(target=work, daemon=True).start()
        d.exec()

    def _show_update_dialog(self) -> None:
        rel = self.latest
        if not rel:
            return
        mandatory = E.is_mandatory(rel)
        d = QtWidgets.QDialog(self)
        d.setWindowTitle("Actualización obligatoria" if mandatory else "Actualización disponible")
        d.setMinimumWidth(520)
        v = QtWidgets.QVBoxLayout(d)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(12)
        head = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel()
        logo.setPixmap(svg_pixmap(LOGO_SVG, 44))
        head.addWidget(logo)
        col = QtWidgets.QVBoxLayout()
        t = QtWidgets.QLabel(f"PocketLens v{rel['version']}")
        t.setStyleSheet("font-size: 17px; font-weight: 700;")
        sub = QtWidgets.QLabel(f"Tienes la v{E.APP_VERSION}")
        sub.setStyleSheet(f"color: {C['text3']};")
        col.addWidget(t)
        col.addWidget(sub)
        head.addLayout(col, 1)
        v.addLayout(head)
        if mandatory:
            warn = QtWidgets.QLabel("Tu versión tiene un problema de seguridad conocido. PocketLens no se puede "
                                    "usar hasta que actualices.", objectName="danger")
            warn.setWordWrap(True)
            v.addWidget(warn)
        notes = QtWidgets.QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(rel["notes"] or "Mejoras y correcciones.")
        notes.setMinimumHeight(180)
        v.addWidget(notes)
        can = E.can_self_update(rel["assets"])
        if not can:
            hint = QtWidgets.QLabel("Esta instalación no se puede actualizar sola: se abrirá la página de descargas.",
                                    objectName="hint")
            hint.setWordWrap(True)
            v.addWidget(hint)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        later = QtWidgets.QPushButton("Salir" if mandatory else "Más tarde", objectName="ghost")
        later.clicked.connect(d.reject)
        go = QtWidgets.QPushButton("Actualizar y reiniciar" if can else "Abrir descargas", objectName="connect")
        go.clicked.connect(d.accept)
        row.addWidget(later)
        row.addWidget(go)
        v.addLayout(row)
        if d.exec() != QtWidgets.QDialog.Accepted:
            if mandatory:
                self._quit()
            return
        if not can:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(rel["page"] or E.RELEASES_URL))
            if mandatory:
                self._quit()
            return

        def done(res):
            if isinstance(res, Exception):
                return self._warn(f"No se pudo actualizar:\n{res}")
            if self.video:
                self._disconnect()
            E.restart()
            self._quit()
        self._run_task(lambda prog: E.self_update(rel["assets"], prog), "Actualizando PocketLens",
                       f"Descargando v{rel['version']}…", done)

    def _update_phone(self, skip_disconnect: bool = False) -> None:
        rel, serial = self.latest, self.serial
        url = E.pick_asset(rel["assets"], "apk") if rel else None
        if not (url and serial and self.adb):
            return
        if not skip_disconnect:
            self._disconnect()
        self.serial = serial

        def done(res, allow=False):
            if isinstance(res, Exception):
                return self._warn(f"No se pudo actualizar la app del teléfono:\n{res}")
            if res == "signature" and not allow:
                r = QtWidgets.QMessageBox.question(
                    self, "Reinstalar app",
                    "La app del teléfono está firmada con otra clave (versión de desarrollo).\n"
                    "Hay que desinstalarla e instalar la nueva; se perderán sus ajustes. ¿Continuar?")
                if r == QtWidgets.QMessageBox.Yes:
                    self._run_task(lambda prog: E.update_phone_app(self.adb, serial, url, prog, True),
                                   "Actualizando teléfono", "Reinstalando la app…", lambda x: done(x, True))
                return
            self.ft["msg"].setText(f"App del teléfono actualizada a v{rel['version']}")
            QtCore.QTimer.singleShot(1500, self._connect)
        self._run_task(lambda prog: E.update_phone_app(self.adb, serial, url, prog), "Actualizando teléfono",
                       f"Descargando e instalando PocketLens v{rel['version']} en el teléfono…", done)

    # ------------------------------------------------------------------ close
    def closeEvent(self, e: QtGui.QCloseEvent) -> None:
        if self.video and self.tray and not self.quitting:
            e.ignore()
            self.hide()
            if not self.tray_hint_shown:
                self.tray.showMessage("PocketLens", "Sigue transmitiendo en segundo plano. "
                                      "Usa el icono de la bandeja para volver o salir.", app_icon(), 4000)
                self.tray_hint_shown = True
            return
        self._save_cfg()
        if self.video:
            self._disconnect()
        self.discovery.stop_ev.set()
        if self.tray:
            self.tray.hide()
        super().closeEvent(e)
        QtWidgets.QApplication.quit()


def main() -> int:
    if E.IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("webcam.adb.client")
        except Exception:  # noqa: BLE001
            pass
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("PocketLens")
    app.setDesktopFileName("pocketlens")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(C["bg"]))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(C["card2"]))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor(C["text"]))
    pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(C["text"]))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(C["text"]))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(C["card2"]))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(C["accent2"]))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
