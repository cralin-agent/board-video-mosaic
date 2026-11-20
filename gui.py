"""Windows folder drop UI. tkinterdnd2 supports folder drag & drop."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    TkinterDnD=None
from pipeline import run_folder

def main():
    root=(TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk())
    root.title("Board Video Mosaic | 板书视频批量压缩")
    root.geometry("780x530")
    folder=tk.StringVar()
    mode=tk.StringVar(value="avif")
    fast=tk.BooleanVar(value=False)
    status=tk.StringVar(value="拖入视频文件夹，或点击「选择文件夹」")
    events=queue.Queue()
    busy=[False]
    ttk.Label(root,text="板书视频 → 逐秒四宫格 → 每视频独立 ZIP",
              font=("Segoe UI",16,"bold")).pack(pady=15)
    box=ttk.Frame(root);box.pack(fill="x",padx=18)
    entry=ttk.Entry(box,textvariable=folder);entry.pack(side="left",fill="x",expand=True,padx=(0,8))
    ttk.Button(box,text="选择文件夹",command=lambda:folder.set(filedialog.askdirectory() or folder.get())).pack(side="right")
    drop=tk.Label(root,text="将包含多个视频的文件夹拖到这里\nDrag a VIDEO FOLDER here",
      height=5,relief="groove",bg="#e8f0f8",font=("Segoe UI",12))
    drop.pack(fill="x",padx=18,pady=12)
    if TkinterDnD is not None:
        drop.drop_target_register(DND_FILES)
        def dropped(event):
            files=root.tk.splitlist(event.data)
            if files:folder.set(files[0])
        drop.dnd_bind("<<Drop>>",dropped)
    else:
        drop.config(text="拖放组件不可用，请使用上方「选择文件夹」")
    opts=ttk.Frame(root);opts.pack(anchor="w",padx=18)
    ttk.Radiobutton(opts,text="彩色 AVIF（保真优先）",variable=mode,value="avif").pack(anchor="w")
    ttk.Radiobutton(opts,text="DSH 二值化（体积最小，可能漏浅色字）",variable=mode,value="dsh").pack(anchor="w")
    ttk.Checkbutton(opts,text="AVIF 快速模式（固定 Q55，跳过逐张质量检查）",variable=fast).pack(anchor="w")
    ttk.Label(root,textvariable=status).pack(anchor="w",padx=18,pady=6)
    log=tk.Text(root,height=10,wrap="word");log.pack(expand=True,fill="both",padx=18,pady=6)
    def write(message):
        log.insert("end",str(message)+"\n");log.see("end")
    def worker(p,algo,speed):
        try:
            result=run_folder(p,algorithm=algo,adaptive=not speed,
                callback=lambda msg: events.put(("log",msg)))
            errors=[x for x in result["results"] if x["status"]=="error"]
            events.put(("done",f"处理完成：{len(result['results'])} 个视频，失败 {len(errors)} 个。输出：{result['output']}"))
        except Exception as exc:
            events.put(("done","运行失败："+str(exc)))
    def start():
        p=Path(folder.get().strip().strip('"'))
        if not p.is_dir():
            messagebox.showerror("错误","请选择存在的视频文件夹");return
        if busy[0]:return
        busy[0]=True;start_btn.configure(state="disabled")
        status.set("正在处理...");write("输入："+str(p))
        threading.Thread(target=worker,args=(p,mode.get(),fast.get()),daemon=True).start()
    start_btn=ttk.Button(root,text="开始批量处理",command=start)
    start_btn.pack(pady=5)
    def poll():
        try:
            while True:
                kind,msg=events.get_nowait();write(msg)
                if kind=="done":
                    status.set(msg);busy[0]=False;start_btn.configure(state="normal")
        except queue.Empty:pass
        root.after(150,poll)
    poll();root.mainloop()
if __name__=="__main__":main()
