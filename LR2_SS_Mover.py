"""
SS Mover  v8
────────────────────────────────────────────────────────
LR2 のスクショを日付フォルダに自動仕分けするツール
必須: pip install watchdog
起動: python ss_mover.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json, os, sys, time, shutil, threading
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

try:
    import winreg; HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

BASE_DIR    = os.path.dirname(os.path.abspath(sys.executable if getattr(sys,"frozen",False) else __file__))
CONFIG_FILE = os.path.join(BASE_DIR, "ss_mover_config.json")
APP_NAME    = "LR2SSMover"
EXE_PATH    = os.path.abspath(sys.argv[0])

DEFAULT_CONFIG = {"ss_source":"", "ss_dest":"", "ss_auto":True}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE,encoding="utf-8") as f:
                return {**DEFAULT_CONFIG,**json.load(f)}
        except: pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_FILE,"w",encoding="utf-8") as f:
        json.dump(cfg,f,ensure_ascii=False,indent=2)

# ── watchdog ハンドラ ─────────────────────────────────
if HAS_WATCHDOG:
    class _SSHandler(FileSystemEventHandler):
        def __init__(self,dest_base,log_cb):
            self._dest=dest_base; self._log=log_cb
        def on_created(self,event):
            if not event.is_directory and event.src_path.lower().endswith(".png"):
                threading.Thread(target=self._move,args=(event.src_path,),daemon=True).start()
        def _move(self,src):
            # LR2 が書き終わるまで最大5秒リトライ
            for attempt in range(10):
                time.sleep(0.5 + attempt * 0.3)
                if not os.path.exists(src):
                    return
                try:
                    today=datetime.now().strftime("%Y-%m-%d")
                    dest_dir=os.path.join(self._dest,today)
                    os.makedirs(dest_dir,exist_ok=True)
                    name=os.path.basename(src)
                    dst=os.path.join(dest_dir,name)
                    if os.path.exists(dst):
                        n,e=os.path.splitext(name)
                        dst=os.path.join(dest_dir,f"{n}_{int(time.time())}{e}")
                    shutil.move(src,dst)
                    self._log(f"✅ {name} → {today}/")
                    return
                except PermissionError:
                    continue   # まだロック中 → リトライ
                except Exception as ex:
                    self._log(f"❌ {ex}"); return
            self._log(f"❌ タイムアウト: {os.path.basename(src)}")

# ── スタートアップ ────────────────────────────────────
STARTUP_KEY=r"Software\Microsoft\Windows\CurrentVersion\Run"
def is_startup_registered():
    if not HAS_WINREG: return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,STARTUP_KEY) as k:
            winreg.QueryValueEx(k,APP_NAME); return True
    except OSError: return False

def set_startup(enable):
    if not HAS_WINREG: return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,STARTUP_KEY,0,winreg.KEY_SET_VALUE) as k:
            if enable: winreg.SetValueEx(k,APP_NAME,0,winreg.REG_SZ,f'"{EXE_PATH}" --minimized')
            else: winreg.DeleteValue(k,APP_NAME)
        return True
    except: return False

# ── App ───────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SS Mover  v8")
        self.resizable(True,False)
        self.cfg=load_config()
        self._ss_observer=None
        self._build_ui()
        self._auto_start_ss()
        if "--minimized" in sys.argv: self.after(200,self.iconify)
        self.protocol("WM_DELETE_WINDOW",self._on_close)

    def _build_ui(self):
        p=ttk.Frame(self); p.pack(fill="both",expand=True)
        p.columnconfigure(0,weight=1)

        def _browse(var,key):
            path=filedialog.askdirectory()
            if path: var.set(path); self.cfg[key]=path; save_config(self.cfg)

        fs=ttk.LabelFrame(p,text="監視元（LR2HD などスクショが保存されるフォルダ）")
        fs.grid(row=0,column=0,padx=14,pady=(14,4),sticky="ew"); fs.columnconfigure(0,weight=1)
        self._var_src=tk.StringVar(value=self.cfg.get("ss_source",""))
        ttk.Entry(fs,textvariable=self._var_src).grid(row=0,column=0,padx=6,pady=6,sticky="ew")
        ttk.Button(fs,text="参照",command=lambda:_browse(self._var_src,"ss_source")).grid(row=0,column=1,padx=4)

        fd=ttk.LabelFrame(p,text="移動先（日付フォルダが自動作成される場所）")
        fd.grid(row=1,column=0,padx=14,pady=4,sticky="ew"); fd.columnconfigure(0,weight=1)
        self._var_dst=tk.StringVar(value=self.cfg.get("ss_dest",""))
        ttk.Entry(fd,textvariable=self._var_dst).grid(row=0,column=0,padx=6,pady=6,sticky="ew")
        ttk.Button(fd,text="参照",command=lambda:_browse(self._var_dst,"ss_dest")).grid(row=0,column=1,padx=4)

        fa=ttk.Frame(p); fa.grid(row=2,column=0,padx=14,pady=4,sticky="w")
        self._var_auto=tk.BooleanVar(value=self.cfg.get("ss_auto",True))
        ttk.Checkbutton(fa,text="ツール起動時に自動で監視を開始する",
                        variable=self._var_auto,command=self._save_auto).pack(side="left")

        self._btn=tk.Button(p,text="▶ 監視を開始する",font=("",11,"bold"),
                            bg="#4CAF50",fg="white",command=self._toggle)
        self._btn.grid(row=3,column=0,padx=14,pady=8,sticky="ew",ipady=6)

        if not HAS_WATCHDOG:
            ttk.Label(p,text="watchdog が必要です: pip install watchdog",
                      foreground="orange").grid(row=4,column=0,padx=14,sticky="w")

        # スタートアップ
        fsu=ttk.LabelFrame(p,text="Windows スタートアップ登録")
        fsu.grid(row=5,column=0,padx=14,pady=4,sticky="ew")
        if HAS_WINREG:
            self._var_startup=tk.BooleanVar(value=is_startup_registered())
            ttk.Checkbutton(fsu,text="Windows起動時に自動起動する（最小化で起動）",
                            variable=self._var_startup,command=self._toggle_startup).grid(padx=10,pady=8,sticky="w")
        else:
            ttk.Label(fsu,text="Windows以外では利用できません",foreground="gray").grid(padx=10,pady=8)

        # ログ
        fl=ttk.LabelFrame(p,text="ログ")
        fl.grid(row=6,column=0,padx=14,pady=4,sticky="nsew"); p.rowconfigure(6,weight=1)
        fl.columnconfigure(0,weight=1); fl.rowconfigure(0,weight=1)
        self._log=tk.Text(fl,height=12,state="disabled",bg="#1a1a1a",fg="#cccccc")
        self._log.grid(row=0,column=0,sticky="nsew")
        sb=ttk.Scrollbar(fl,orient="vertical",command=self._log.yview)
        sb.grid(row=0,column=1,sticky="ns"); self._log.configure(yscrollcommand=sb.set)

    def _save_auto(self):
        self.cfg["ss_auto"]=self._var_auto.get(); save_config(self.cfg)

    def _log_append(self,msg):
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end",f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self._log.see("end"); self._log.configure(state="disabled")
        self.after(0,_do)

    def _toggle(self):
        if self._ss_observer and self._ss_observer.is_alive():
            self._ss_observer.stop(); self._ss_observer.join()
            self._ss_observer=None
            self._btn.configure(text="▶ 監視を開始する",bg="#4CAF50")
            self._log_append("🛑 監視停止")
        else:
            self._start()

    def _start(self):
        if not HAS_WATCHDOG:
            messagebox.showerror("エラー","pip install watchdog が必要です"); return False
        src=self._var_src.get(); dst=self._var_dst.get()
        if not src or not os.path.exists(src):
            messagebox.showwarning("未設定","監視元フォルダを設定してください"); return False
        if not dst:
            messagebox.showwarning("未設定","移動先フォルダを設定してください"); return False
        os.makedirs(dst,exist_ok=True)
        self.cfg["ss_source"]=src; self.cfg["ss_dest"]=dst; save_config(self.cfg)
        handler=_SSHandler(dst,self._log_append)
        self._ss_observer=Observer()
        self._ss_observer.schedule(handler,src,recursive=False)
        self._ss_observer.start()
        self._btn.configure(text="■ 監視を停止する",bg="#f44336")
        self._log_append(f"🚀 監視開始 → {src}")
        return True

    def _auto_start_ss(self):
        if self.cfg.get("ss_auto",True): self._start()

    def _toggle_startup(self):
        if not set_startup(self._var_startup.get()):
            messagebox.showerror("エラー","スタートアップ登録に失敗しました")
            self._var_startup.set(not self._var_startup.get())

    def _on_close(self):
        if self._ss_observer and self._ss_observer.is_alive():
            self._ss_observer.stop(); self._ss_observer.join()
        self.destroy()

if __name__=="__main__":
    App().mainloop()
