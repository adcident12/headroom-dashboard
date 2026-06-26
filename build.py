"""Build Headroom into a standalone executable using PyInstaller."""

import os
import subprocess
import sys

def main():
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Find customtkinter data directory
    import customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)

    is_win = sys.platform == "win32"
    is_mac = sys.platform == "darwin"

    app_name = "Headroom"
    script = "headroom_app.py"

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        f"--name={app_name}",
        f"--add-data={ctk_path}{os.pathsep}customtkinter",
    ]

    # Hidden imports for pystray backends and customtkinter
    hidden = [
        "pystray",
        "pystray._util",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "customtkinter",
        "usage_history",
    ]

    if is_win:
        hidden += ["pystray._win32"]
        if os.path.isfile("headroom.ico"):
            args.append(f"--icon=headroom.ico")
    elif is_mac:
        hidden += ["pystray._darwin"]
        if os.path.isfile("headroom.icns"):
            args.append(f"--icon=headroom.icns")
        elif os.path.isfile("headroom.png"):
            args.append(f"--icon=headroom.png")
    else:
        hidden += ["pystray._xorg", "pystray._appindicator"]

    for h in hidden:
        args.append(f"--hidden-import={h}")

    args.append(script)

    print(f"Building {app_name} for {sys.platform}...")
    print(f"Command: {' '.join(args)}")
    print()

    rc = subprocess.call(args)

    if rc == 0:
        dist_dir = os.path.join("dist", app_name + (".exe" if is_win else ""))
        if is_mac:
            dist_dir = os.path.join("dist", app_name + ".app")
        print(f"\nBuild successful! Output: {dist_dir}")
    else:
        print(f"\nBuild failed with exit code {rc}")
        sys.exit(rc)


if __name__ == "__main__":
    main()
