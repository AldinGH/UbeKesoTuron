import argparse
import socket
import threading
import webbrowser

import server


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description="Run UbeKeso Cart")
    ap.add_argument("--lan", action="store_true", help="let other devices on your Wi-Fi connect")
    ap.add_argument("--port", type=int, default=8000, help="first port to try (default 8000)")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = ap.parse_args()

    admin_created = server.load()
    httpd, port = server.make_server("0.0.0.0" if args.lan else "127.0.0.1", args.port)
    url = "http://localhost:{}/index.html".format(port)

    print("UbeKeso Cart is running at", url)
    if args.lan:
        ip = lan_ip()
        if ip:
            print("On a phone (same Wi-Fi) open: http://{}:{}/index.html".format(ip, port))
        print("Anyone on your network can reach this server. Change the owner password first.")
    admin = next(u for u in server.DB["users"].values() if u["role"] == "admin")
    if admin["must_change"]:
        print("")
        print("Owner (admin) login:  {}  /  {}".format(admin["email"], server.ADMIN_PASSWORD))
        print("This is the default password. Sign in and change it right away.")
    elif admin_created:
        print("Owner (admin) account created for", admin["email"])
    print("")
    if server.mail_ready():
        print("Gmail sending is ON: sign up and password reset codes are emailed.")
    else:
        print("Gmail sending is OFF (demo mode): codes are shown in the app and printed here.")
        print("To turn it on, copy mail_settings.example.json to mail_settings.json and fill it in (see README).")
    print("Your data is saved in data.json (daily copies in the backups folder). Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
