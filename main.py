import hashlib
import json
import os
import socket
import struct
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from kivy.app import App
from kivy.clock import mainthread
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput


PORT = 50022
CHUNK_SIZE = 64 * 1024
SOCKET_TIMEOUT = 3.0

COLORS = {
    "bg": (0.94, 0.97, 1.0, 1),
    "surface": (1, 1, 1, 1),
    "surface_soft": (0.97, 0.985, 1.0, 1),
    "primary": (0.06, 0.43, 0.86, 1),
    "primary_dark": (0.03, 0.20, 0.42, 1),
    "success": (0.04, 0.55, 0.33, 1),
    "warning": (0.95, 0.56, 0.12, 1),
    "danger": (0.86, 0.16, 0.18, 1),
    "text": (0.06, 0.10, 0.16, 1),
    "muted": (0.42, 0.48, 0.56, 1),
    "border": (0.83, 0.88, 0.94, 1),
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/DroidSansFallback.ttf",
]

APP_FONT = "Roboto"
for font_path in FONT_CANDIDATES:
    if os.path.exists(font_path):
        LabelBase.register(name="FileLinkCJK", fn_regular=font_path)
        APP_FONT = "FileLinkCJK"
        break


def recvall(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("连接已经断开")
        data.extend(chunk)
    return bytes(data)


def send_json(sock, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("!I", len(body)) + body)


def recv_json(sock):
    header = recvall(sock, 4)
    size = struct.unpack("!I", header)[0]
    return json.loads(recvall(sock, size).decode("utf-8"))


def sha256_file(path, stop_event=None):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            if stop_event and stop_event.is_set():
                raise InterruptedError("用户取消")
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest(), os.path.getsize(path)


def unique_path(folder, filename):
    folder = Path(folder)
    target = folder / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    index = 1
    while True:
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def format_bytes(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def format_seconds(seconds):
    if seconds <= 0 or seconds == float("inf"):
        return "--"
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}时{minutes}分"
    if minutes:
        return f"{minutes}分{sec}秒"
    return f"{sec}秒"


def get_local_ips():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        default_ip = probe.getsockname()[0]
        probe.close()
        if default_ip not in ips and not default_ip.startswith("127."):
            ips.insert(0, default_ip)
    except Exception:
        pass

    return ips or ["127.0.0.1"]


class Card(BoxLayout):
    def __init__(
        self,
        bg_color=COLORS["surface"],
        border_color=COLORS["border"],
        radius=18,
        padding=16,
        spacing=10,
        **kwargs,
    ):
        super().__init__(padding=dp(padding), spacing=dp(spacing), **kwargs)
        self.bg_color = bg_color
        self.border_color = border_color
        self.radius = dp(radius)
        with self.canvas.before:
            Color(*self.bg_color)
            self._bg = RoundedRectangle(radius=[(self.radius, self.radius)] * 4)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _update_canvas(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size


class RoundedButton(Button):
    def __init__(
        self,
        bg_color=COLORS["primary"],
        text_color=(1, 1, 1, 1),
        radius=14,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.color = text_color
        self.bold = True
        self.font_name = APP_FONT
        self.font_size = sp(15)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.radius = dp(radius)
        self.size_hint_y = None
        self.height = dp(kwargs.pop("height", 46))
        with self.canvas.before:
            Color(*self.bg_color)
            self._bg = RoundedRectangle(radius=[(self.radius, self.radius)] * 4)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _update_canvas(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size


class AppLabel(Label):
    def __init__(self, color=COLORS["text"], font_size_value=14, **kwargs):
        super().__init__(**kwargs)
        self.font_name = APP_FONT
        self.color = color
        self.font_size = sp(font_size_value)
        self.halign = kwargs.get("halign", "left")
        self.valign = kwargs.get("valign", "middle")
        self.bind(size=self._sync_text)

    def _sync_text(self, *_):
        self.text_size = (self.width, self.height if self.shorten else None)


class SectionTitle(AppLabel):
    def __init__(self, text, **kwargs):
        super().__init__(
            text=text,
            color=COLORS["text"],
            font_size_value=17,
            bold=True,
            size_hint_y=None,
            height=dp(28),
            **kwargs,
        )


class MutedLabel(AppLabel):
    def __init__(self, **kwargs):
        super().__init__(color=COLORS["muted"], font_size_value=13, **kwargs)


class Pill(Label):
    def __init__(self, text="", bg_color=COLORS["surface_soft"], color=COLORS["primary_dark"], **kwargs):
        super().__init__(text=text, color=color, bold=True, font_size=sp(12), **kwargs)
        self.font_name = APP_FONT
        self.size_hint_y = None
        self.height = dp(28)
        self.halign = "center"
        self.valign = "middle"
        self.bind(size=self._sync_text)
        with self.canvas.before:
            Color(*bg_color)
            self._bg = RoundedRectangle(radius=[(dp(14), dp(14))] * 4)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _sync_text(self, *_):
        self.text_size = self.size

    def _update_canvas(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size


class ModernTextInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.multiline = False
        self.font_name = APP_FONT
        self.font_size = sp(15)
        self.foreground_color = COLORS["text"]
        self.background_color = (1, 1, 1, 1)
        self.cursor_color = COLORS["primary"]
        self.padding = [dp(12), dp(10), dp(12), dp(10)]
        self.size_hint_y = None
        self.height = dp(46)


class FileTransferApp(App):
    def build(self):
        Window.clearcolor = COLORS["bg"]
        self.cancel_event = threading.Event()
        self.server_sock = None
        self.active_sock = None
        self.selected_file = None
        self.save_dir = str(Path.home() / "Downloads")
        self.temp_zip = None
        self.local_ips = get_local_ips()
        self.current_start_time = None
        self.current_start_offset = 0

        root = BoxLayout(orientation="vertical", padding=0, spacing=0)
        root.add_widget(self.build_header())

        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(18)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        content.add_widget(self.build_connection_card())
        content.add_widget(self.build_file_card())
        content.add_widget(self.build_transfer_card())
        content.add_widget(self.build_log_card())

        scroll.add_widget(content)
        root.add_widget(scroll)
        return root

    def build_header(self):
        header = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(14)],
            spacing=dp(8),
            size_hint_y=None,
            height=dp(128),
        )
        with header.canvas.before:
            Color(*COLORS["primary_dark"])
            header._bg = RoundedRectangle(radius=[(0, 0), (0, 0), (dp(24), dp(24)), (dp(24), dp(24))])
        header.bind(pos=lambda obj, *_: setattr(obj._bg, "pos", obj.pos))
        header.bind(size=lambda obj, *_: setattr(obj._bg, "size", obj.size))

        top = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        title_box = BoxLayout(orientation="vertical", spacing=dp(2))
        title_box.add_widget(
            Label(
                text="FileLink 速传",
                font_name=APP_FONT,
                color=(1, 1, 1, 1),
                bold=True,
                font_size=sp(24),
                halign="left",
                valign="middle",
            )
        )
        top.add_widget(title_box)
        top.add_widget(Pill(text=f"TCP:{PORT}", bg_color=(1, 1, 1, 0.14), color=(1, 1, 1, 1), size_hint_x=0.25))
        header.add_widget(top)

        subtitle = Label(
            text="面对面高速直传 · 断点续传 · SHA-256 校验",
            font_name=APP_FONT,
            color=(0.78, 0.87, 1, 1),
            font_size=sp(14),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        subtitle.bind(size=lambda obj, *_: setattr(obj, "text_size", obj.size))
        header.add_widget(subtitle)
        return header

    def build_connection_card(self):
        card = Card(orientation="vertical", size_hint_y=None)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(SectionTitle("1. 连接设备"))

        ip_text = " / ".join(self.local_ips)
        self.local_ip_label = MutedLabel(
            text=f"我的 IP：{ip_text}",
            size_hint_y=None,
            height=dp(34),
        )
        card.add_widget(self.local_ip_label)

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(Pill(text="对方 IP", size_hint_x=0.28))
        self.ip_input = ModernTextInput(text="127.0.0.1", hint_text="例如 192.168.1.23")
        row.add_widget(self.ip_input)
        card.add_widget(row)

        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        listen_btn = RoundedButton(text="开始接收", bg_color=COLORS["success"])
        listen_btn.bind(on_press=self.start_receiver)
        actions.add_widget(listen_btn)

        refresh_btn = RoundedButton(
            text="刷新 IP",
            bg_color=(0.90, 0.94, 0.99, 1),
            text_color=COLORS["primary_dark"],
        )
        refresh_btn.bind(on_press=self.refresh_local_ip)
        actions.add_widget(refresh_btn)
        card.add_widget(actions)

        note = MutedLabel(
            text="接收方先点“开始接收”，发送方输入这里显示的 IP 后发送。",
            size_hint_y=None,
            height=dp(34),
        )
        card.add_widget(note)
        return card

    def build_file_card(self):
        card = Card(orientation="vertical", size_hint_y=None)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(SectionTitle("2. 文件与保存"))

        self.file_label = AppLabel(
            text="待发送文件：未选择",
            shorten=True,
            shorten_from="right",
            max_lines=1,
            size_hint_y=None,
            height=dp(42),
        )
        card.add_widget(self.file_label)

        self.save_label = AppLabel(
            text=f"保存位置：{self.save_dir}",
            color=COLORS["muted"],
            font_size_value=13,
            shorten=True,
            shorten_from="left",
            max_lines=1,
            size_hint_y=None,
            height=dp(42),
        )
        card.add_widget(self.save_label)

        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        choose_file_btn = RoundedButton(text="选择文件")
        choose_file_btn.bind(on_press=lambda *_: self.open_file_picker())
        actions.add_widget(choose_file_btn)

        save_btn = RoundedButton(
            text="保存位置",
            bg_color=(0.90, 0.94, 0.99, 1),
            text_color=COLORS["primary_dark"],
        )
        save_btn.bind(on_press=lambda *_: self.open_folder_picker())
        actions.add_widget(save_btn)
        card.add_widget(actions)

        options = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        self.compress_box = CheckBox(size_hint_x=None, width=dp(42))
        self.unzip_box = CheckBox(active=True, size_hint_x=None, width=dp(42))
        options.add_widget(self.make_option("发送前压缩 ZIP", self.compress_box))
        options.add_widget(self.make_option("接收后自动解压", self.unzip_box))
        card.add_widget(options)
        return card

    def make_option(self, text, checkbox):
        box = Card(
            orientation="horizontal",
            bg_color=COLORS["surface_soft"],
            border_color=(0.90, 0.93, 0.97, 1),
            radius=14,
            padding=8,
            spacing=4,
        )
        box.add_widget(checkbox)
        box.add_widget(AppLabel(text=text, font_size_value=12))
        return box

    def build_transfer_card(self):
        card = Card(orientation="vertical", size_hint_y=None)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(SectionTitle("3. 传输监控"))

        self.status_label = AppLabel(
            text="准备就绪",
            bold=True,
            font_size_value=15,
            size_hint_y=None,
            height=dp(34),
        )
        card.add_widget(self.status_label)

        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(20))
        card.add_widget(self.progress)

        stats = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(58))
        self.percent_label = self.make_stat("进度", "0%")
        self.speed_label = self.make_stat("速度", "--")
        self.eta_label = self.make_stat("剩余", "--")
        stats.add_widget(self.percent_label)
        stats.add_widget(self.speed_label)
        stats.add_widget(self.eta_label)
        card.add_widget(stats)

        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        send_btn = RoundedButton(text="立即发送", bg_color=COLORS["primary"])
        send_btn.bind(on_press=self.start_sender)
        actions.add_widget(send_btn)

        cancel_btn = RoundedButton(text="取消传输", bg_color=COLORS["danger"])
        cancel_btn.bind(on_press=self.cancel_transfer)
        actions.add_widget(cancel_btn)
        card.add_widget(actions)
        return card

    def make_stat(self, title, value):
        box = Card(
            orientation="vertical",
            bg_color=COLORS["surface_soft"],
            border_color=(0.90, 0.93, 0.97, 1),
            radius=14,
            padding=8,
            spacing=2,
        )
        box.title = MutedLabel(text=title, size_hint_y=None, height=dp(18), halign="center")
        box.value = AppLabel(
            text=value,
            color=COLORS["primary_dark"],
            bold=True,
            font_size_value=14,
            size_hint_y=None,
            height=dp(22),
            halign="center",
        )
        box.add_widget(box.title)
        box.add_widget(box.value)
        return box

    def build_log_card(self):
        card = Card(orientation="vertical", size_hint_y=None, height=dp(230))
        card.add_widget(SectionTitle("运行记录"))
        self.log_label = AppLabel(
            text="欢迎使用 FileLink。请确保两台设备在同一个校园网或局域网内。",
            color=COLORS["muted"],
            font_size_value=13,
            size_hint_y=None,
            halign="left",
            valign="top",
        )
        self.log_label.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
        self.log_label.bind(texture_size=lambda obj, size: setattr(obj, "height", max(size[1] + dp(12), dp(150))))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.log_label)
        card.add_widget(scroll)
        return card

    def refresh_local_ip(self, *_):
        self.local_ips = get_local_ips()
        self.local_ip_label.text = f"我的 IP：{' / '.join(self.local_ips)}"
        self.log("已刷新本机 IP。")

    def open_file_picker(self):
        chooser = FileChooserIconView(path=str(Path.home()))
        popup = self.make_picker_popup("选择要发送的文件", chooser)

        def choose(*_):
            if chooser.selection:
                self.selected_file = chooser.selection[0]
                size_text = format_bytes(os.path.getsize(self.selected_file))
                self.file_label.text = f"待发送文件：{os.path.basename(self.selected_file)}  ({size_text})"
                self.log(f"已选择文件：{self.selected_file}")
                popup.dismiss()

        popup.ok_button.bind(on_press=choose)
        popup.open()

    def open_folder_picker(self):
        chooser = FileChooserIconView(path=self.save_dir, dirselect=True)
        popup = self.make_picker_popup("选择接收保存目录", chooser)

        def choose(*_):
            selected = chooser.selection[0] if chooser.selection else chooser.path
            if os.path.isdir(selected):
                self.save_dir = selected
                self.save_label.text = f"保存位置：{self.save_dir}"
                self.log(f"保存位置已设置为：{self.save_dir}")
                popup.dismiss()

        popup.ok_button.bind(on_press=choose)
        popup.open()

    def make_picker_popup(self, title, chooser):
        panel = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        panel.add_widget(chooser)
        button_row = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        cancel = RoundedButton(
            text="取消",
            bg_color=(0.90, 0.94, 0.99, 1),
            text_color=COLORS["primary_dark"],
        )
        ok = RoundedButton(text="确定", bg_color=COLORS["primary"])
        button_row.add_widget(cancel)
        button_row.add_widget(ok)
        panel.add_widget(button_row)
        popup = Popup(title=title, content=panel, size_hint=(0.92, 0.9))
        popup.ok_button = ok
        cancel.bind(on_press=lambda *_: popup.dismiss())
        return popup

    def start_receiver(self, *_):
        self.cancel_event.clear()
        threading.Thread(target=self.receiver_worker, daemon=True).start()

    def start_sender(self, *_):
        if not self.selected_file:
            self.log("请先选择要发送的文件。")
            self.set_status("请先选择文件", COLORS["warning"])
            return
        self.cancel_event.clear()
        threading.Thread(target=self.sender_worker, daemon=True).start()

    def cancel_transfer(self, *_):
        self.cancel_event.set()
        for sock in (self.active_sock, self.server_sock):
            try:
                if sock:
                    sock.shutdown(socket.SHUT_RDWR)
                    sock.close()
            except Exception:
                pass
        self.set_status("已取消，断点保留", COLORS["warning"])
        self.log("已发出取消请求。再次传输同一文件会尝试断点续传。")

    def receiver_worker(self):
        try:
            self.reset_transfer_ui()
            self.set_status(f"监听中 0.0.0.0:{PORT}", COLORS["primary"])
            self.log(f"正在监听 0.0.0.0:{PORT}，等待发送方连接...")
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("0.0.0.0", PORT))
            self.server_sock.listen(1)
            conn, addr = self.server_sock.accept()
            self.active_sock = conn
            conn.settimeout(SOCKET_TIMEOUT)
            self.log(f"已连接发送方：{addr[0]}")

            meta = recv_json(conn)
            filename = meta["filename"]
            total_size = int(meta["size"])
            digest = meta["sha256"]
            compressed = bool(meta.get("compressed"))

            final_path = unique_path(self.save_dir, filename)
            part_path = Path(str(final_path) + ".part")
            state_path = Path(str(final_path) + ".state.json")
            offset = 0

            if part_path.exists() and state_path.exists():
                old = json.loads(state_path.read_text(encoding="utf-8"))
                if old.get("sha256") == digest and old.get("filename") == filename:
                    offset = min(part_path.stat().st_size, total_size)

            state_path.write_text(
                json.dumps(
                    {"filename": filename, "size": total_size, "sha256": digest},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            send_json(conn, {"ok": True, "offset": offset})

            bytes_received = offset
            mode = "ab" if offset else "wb"
            self.begin_meter(offset)
            self.log(f"开始接收：{filename}，从 {format_bytes(offset)} 处继续。")
            with open(part_path, mode) as f:
                while bytes_received < total_size:
                    if self.cancel_event.is_set():
                        raise InterruptedError("用户取消")
                    to_read = min(CHUNK_SIZE, total_size - bytes_received)
                    chunk = conn.recv(to_read)
                    if not chunk:
                        raise ConnectionError("连接中断，已保留断点文件")
                    f.write(chunk)
                    bytes_received += len(chunk)
                    self.show_progress(bytes_received, total_size, f"接收 {filename}")

            self.set_status("正在校验 SHA-256", COLORS["primary"])
            self.log("正在校验文件签名...")
            actual_digest, _ = sha256_file(part_path, self.cancel_event)
            if actual_digest != digest:
                self.set_status("校验失败", COLORS["danger"])
                self.log("校验失败：文件可能损坏，请重新传输。")
                return

            part_path.replace(final_path)
            state_path.unlink(missing_ok=True)
            send_json(conn, {"done": True, "sha256": actual_digest})
            self.show_progress(total_size, total_size, f"完成 {filename}")
            self.set_status("接收完成，校验通过", COLORS["success"])
            self.log(f"接收完成并已保存：{final_path}")

            if compressed and self.unzip_box.active:
                self.unzip_received(final_path)
        except InterruptedError:
            self.set_status("接收已取消", COLORS["warning"])
            self.log("接收已取消，断点文件已保留。")
        except Exception as exc:
            self.set_status("接收失败", COLORS["danger"])
            self.log(f"接收失败：{exc}")
        finally:
            self.close_sockets()

    def sender_worker(self):
        send_path = self.selected_file
        try:
            self.reset_transfer_ui()
            if self.compress_box.active:
                self.set_status("正在压缩文件", COLORS["primary"])
                send_path = self.make_zip(self.selected_file)
                self.log(f"已生成压缩文件：{send_path}")

            self.set_status("正在生成 SHA-256", COLORS["primary"])
            self.log("正在生成文件签名...")
            digest, total_size = sha256_file(send_path, self.cancel_event)
            filename = os.path.basename(send_path)

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.active_sock = sock
            sock.settimeout(SOCKET_TIMEOUT)
            target_ip = self.ip_input.text.strip()
            self.set_status(f"连接 {target_ip}", COLORS["primary"])
            self.log(f"正在连接 {target_ip}:{PORT} ...")
            sock.connect((target_ip, PORT))

            send_json(
                sock,
                {
                    "op": "offer",
                    "filename": filename,
                    "size": total_size,
                    "sha256": digest,
                    "compressed": self.compress_box.active,
                    "chunk_size": CHUNK_SIZE,
                },
            )
            reply = recv_json(sock)
            if not reply.get("ok"):
                self.set_status("接收方拒绝", COLORS["danger"])
                self.log("接收方拒绝了文件。")
                return

            offset = int(reply.get("offset", 0))
            self.begin_meter(offset)
            self.log(f"开始发送：{filename}，从 {format_bytes(offset)} 处继续。")
            bytes_sent = offset
            with open(send_path, "rb") as f:
                f.seek(offset)
                while bytes_sent < total_size:
                    if self.cancel_event.is_set():
                        raise InterruptedError("用户取消")
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    bytes_sent += len(chunk)
                    self.show_progress(bytes_sent, total_size, f"发送 {filename}")

            final_reply = recv_json(sock)
            if final_reply.get("sha256") == digest:
                self.show_progress(total_size, total_size, f"完成 {filename}")
                self.set_status("发送完成，校验通过", COLORS["success"])
                self.log("发送完成，接收方校验通过。")
            else:
                self.set_status("等待校验失败", COLORS["warning"])
                self.log("发送完成，但未收到接收方校验通过确认。")
        except InterruptedError:
            self.set_status("发送已取消", COLORS["warning"])
            self.log("发送已取消。")
        except Exception as exc:
            self.set_status("发送失败", COLORS["danger"])
            self.log(f"发送失败：{exc}")
        finally:
            self.close_sockets()
            self.cleanup_temp_zip()

    def make_zip(self, file_path):
        source = Path(file_path)
        temp_dir = Path(tempfile.gettempdir())
        zip_path = temp_dir / f"{source.stem}_fast_transfer.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(source, arcname=source.name)
        self.temp_zip = str(zip_path)
        return str(zip_path)

    def unzip_received(self, zip_path):
        try:
            extract_dir = Path(zip_path).with_suffix("")
            extract_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            self.log(f"已自动解压到：{extract_dir}")
        except Exception as exc:
            self.log(f"自动解压失败：{exc}")

    def cleanup_temp_zip(self):
        if self.temp_zip:
            try:
                os.remove(self.temp_zip)
            except OSError:
                pass
            self.temp_zip = None

    def close_sockets(self):
        for attr in ("active_sock", "server_sock"):
            sock = getattr(self, attr, None)
            try:
                if sock:
                    sock.close()
            except Exception:
                pass
            setattr(self, attr, None)

    @mainthread
    def begin_meter(self, offset):
        self.current_start_time = time.monotonic()
        self.current_start_offset = offset

    @mainthread
    def reset_transfer_ui(self):
        self.progress.value = 0
        self.percent_label.value.text = "0%"
        self.speed_label.value.text = "--"
        self.eta_label.value.text = "--"
        self.current_start_time = time.monotonic()
        self.current_start_offset = 0

    @mainthread
    def set_status(self, text, color):
        self.status_label.text = text
        self.status_label.color = color

    @mainthread
    def show_progress(self, done, total, label):
        pct = int(done * 100 / total) if total else 0
        elapsed = max(time.monotonic() - (self.current_start_time or time.monotonic()), 0.001)
        session_done = max(done - self.current_start_offset, 0)
        speed = session_done / elapsed
        eta = (total - done) / speed if speed > 1 else float("inf")
        self.progress.value = pct
        self.percent_label.value.text = f"{pct}%"
        self.speed_label.value.text = f"{format_bytes(speed)}/s"
        self.eta_label.value.text = format_seconds(eta)
        self.status_label.text = f"{label} · {format_bytes(done)} / {format_bytes(total)}"
        self.status_label.color = COLORS["primary_dark"]

    @mainthread
    def log(self, message):
        now = time.strftime("%H:%M:%S")
        lines = (self.log_label.text + f"\n[{now}] {message}").splitlines()
        self.log_label.text = "\n".join(lines[-80:])


if __name__ == "__main__":
    FileTransferApp().run()
