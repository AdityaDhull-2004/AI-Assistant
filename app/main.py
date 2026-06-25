"""Native desktop UI (PySide6): chat + voice, streaming replies, system tray."""
import sys
import threading

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame, QMessageBox, QSystemTrayIcon,
    QMenu, QStyle, QCheckBox,
)

from . import config, tools, stt, tts
from .agent import Agent


# ---------------- worker threads ----------------
class AgentThread(QThread):
    token = Signal(str)
    toolUsed = Signal(str, object)
    finishedReply = Signal(str)
    failed = Signal(str)
    confirmAsked = Signal(str)

    def __init__(self, agent, text):
        super().__init__()
        self.agent = agent
        self.text = text
        self._ev = threading.Event()
        self._result = False

    def confirm(self, desc):
        self._result = False
        self._ev.clear()
        self.confirmAsked.emit(desc)
        self._ev.wait()
        return self._result

    def resolve(self, ok):
        self._result = ok
        self._ev.set()

    def run(self):
        tools.CONFIRM_FN = self.confirm
        try:
            reply = self.agent.run(self.text, on_token=self.token.emit,
                                   on_tool=lambda n, a: self.toolUsed.emit(n, a))
            self.finishedReply.emit(reply)
        except Exception as e:
            self.failed.emit(str(e))


class RecordThread(QThread):
    transcribed = Signal(str)
    failed = Signal(str)

    def run(self):
        try:
            from . import audio
            a = audio.record_until_silence()
            self.transcribed.emit(stt.transcribe(a) if a is not None else "")
        except Exception as e:
            self.failed.emit(str(e))


# ---------------- main window ----------------
STYLE = """
QMainWindow, QWidget#root { background: #0f1115; }
QLabel#title { color:#e8eaed; font-size:16px; font-weight:600; }
QLabel#status { color:#8a90a0; font-size:11px; }
QScrollArea { border:none; }
QWidget#chat { background:#0f1115; }
QLabel.user { background:#2563eb; color:white; border-radius:12px; padding:9px 12px; font-size:13px; }
QLabel.bot  { background:#1c2030; color:#e8eaed; border-radius:12px; padding:9px 12px; font-size:13px; }
QLineEdit { background:#1c2030; color:#e8eaed; border:1px solid #2a3040; border-radius:18px;
            padding:9px 14px; font-size:13px; }
QPushButton { background:#2563eb; color:white; border:none; border-radius:18px; padding:9px 16px; font-size:13px; }
QPushButton:hover { background:#1d4ed8; }
QPushButton#mic { background:#1c2030; }
QPushButton#mic:hover { background:#2a3040; }
QPushButton#mic[recording="true"] { background:#dc2626; }
QCheckBox { color:#8a90a0; font-size:11px; }
"""


class Assistant(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Assistant")
        self.resize(560, 720)
        self.agent = Agent()
        self.cur_bot = None      # streaming assistant label
        self.busy = False
        self.athread = None
        self.rthread = None

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # header
        hdr = QVBoxLayout()
        hdr.addWidget(QLabel("AI Assistant", objectName="title"))
        prov = ", ".join(config.providers_configured()) or "NO API KEYS - add them to .env"
        self.status = QLabel(f"Providers: {prov}", objectName="status")
        hdr.addWidget(self.status)
        layout.addLayout(hdr)

        # chat area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.chat = QWidget(objectName="chat")
        self.chat_l = QVBoxLayout(self.chat)
        self.chat_l.setAlignment(Qt.AlignTop)
        self.chat_l.setSpacing(8)
        self.scroll.setWidget(self.chat)
        layout.addWidget(self.scroll, 1)

        # input row
        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="Type a command, or press the mic to talk...")
        self.input.returnPressed.connect(self.on_send)
        self.mic = QPushButton("Mic", objectName="mic")
        self.mic.clicked.connect(self.on_mic)
        self.send = QPushButton("Send")
        self.send.clicked.connect(self.on_send)
        row.addWidget(self.input, 1)
        row.addWidget(self.mic)
        row.addWidget(self.send)
        layout.addLayout(row)

        # options row
        opt = QHBoxLayout()
        self.speak_cb = QCheckBox("Speak replies")
        self.speak_cb.setChecked(True)
        self.speak_cb.toggled.connect(lambda v: tts.set_enabled(v))
        opt.addWidget(self.speak_cb)
        opt.addStretch(1)
        layout.addLayout(opt)

        self.setStyleSheet(STYLE)
        self._setup_tray()

        if not self.agent.llm.available():
            self.add_msg("bot", "No API keys found. Add GROQ_API_KEY / GEMINI_API_KEY to the .env "
                                 "file and restart. (See README.)")
        else:
            self.add_msg("bot", "Ready. Type or press the mic and tell me what to do.")

    # ---- UI helpers ----
    def add_msg(self, role, text):
        wrap = QHBoxLayout()
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setProperty("class", "user" if role == "user" else "bot")
        lbl.setMaximumWidth(420)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            hl.addStretch(1)
            hl.addWidget(lbl)
        else:
            hl.addWidget(lbl)
            hl.addStretch(1)
        self.chat_l.addWidget(holder)
        QTimer.singleShot(30, self._scroll_bottom)
        return lbl

    def _scroll_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_busy(self, on):
        self.busy = on
        self.input.setEnabled(not on)
        self.send.setEnabled(not on)
        self.mic.setEnabled(not on)

    # ---- actions ----
    def on_send(self):
        text = self.input.text().strip()
        if not text or self.busy:
            return
        if not self.agent.llm.available():
            self.add_msg("bot", "I can't run without API keys. Add them to .env and restart.")
            return
        self.input.clear()
        self.add_msg("user", text)
        self.cur_bot = None
        self.status.setText("Thinking...")
        self.set_busy(True)
        self.athread = AgentThread(self.agent, text)
        self.athread.token.connect(self.on_token)
        self.athread.toolUsed.connect(self.on_tool)
        self.athread.finishedReply.connect(self.on_reply)
        self.athread.failed.connect(self.on_error)
        self.athread.confirmAsked.connect(self.on_confirm)
        self.athread.start()

    def on_token(self, t):
        if self.cur_bot is None:
            self.cur_bot = self.add_msg("bot", "")
        self.cur_bot.setText(self.cur_bot.text() + t)
        self._scroll_bottom()

    def on_tool(self, name, args):
        self.status.setText(f"Using {name}...")

    def on_reply(self, reply):
        if self.cur_bot is None and reply:
            self.add_msg("bot", reply)
        prov = self.agent.llm.active or ""
        self.status.setText(f"Provider: {prov}")
        self.set_busy(False)
        if tts.is_enabled() and reply:
            threading.Thread(target=tts.speak, args=(reply,), daemon=True).start()

    def on_error(self, err):
        self.add_msg("bot", f"Error: {err}")
        self.status.setText("Error")
        self.set_busy(False)

    def on_confirm(self, desc):
        res = QMessageBox.question(self, "Confirm action", desc + "\n\nProceed?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if self.athread:
            self.athread.resolve(res == QMessageBox.Yes)

    def on_mic(self):
        if self.busy:
            return
        self.mic.setProperty("recording", "true")
        self.mic.setStyle(self.mic.style())
        self.mic.setText("...")
        self.status.setText("Listening...")
        self.set_busy(True)
        self.rthread = RecordThread()
        self.rthread.transcribed.connect(self.on_transcribed)
        self.rthread.failed.connect(self.on_error)
        self.rthread.start()

    def on_transcribed(self, text):
        self.mic.setProperty("recording", "false")
        self.mic.setStyle(self.mic.style())
        self.mic.setText("Mic")
        self.set_busy(False)
        if text:
            self.input.setText(text)
            self.on_send()
        else:
            self.status.setText("(no speech detected)")

    # ---- tray ----
    def _setup_tray(self):
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("AI Assistant")
        menu = QMenu()
        show = QAction("Show", self); show.triggered.connect(self.showNormal)
        quit_ = QAction("Quit", self); quit_.triggered.connect(QApplication.quit)
        menu.addAction(show); menu.addAction(quit_)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.showNormal() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def closeEvent(self, e):
        # closing the window quits the app
        self.tray.hide()
        QApplication.quit()
        e.accept()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = Assistant()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
